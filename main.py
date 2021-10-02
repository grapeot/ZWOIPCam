from picamera import PiCamera
from time import sleep, time
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from fractions import Fraction
from os.path import join, exists
from os import mkdir
from threading import Condition, Thread
from http import server
from Streaming import StreamingOutput, StreamingServer, StreamingHandler
from queue import Queue
from copy import deepcopy
from sys import exit
import socketserver
import json
import requests
import math
import requests
import logging
import logging.handlers
import sys
import numpy as np
import zwoasi as asi

# Set up logging
logger = logging.getLogger(__name__)
formatter = logging.Formatter('%(asctime)s : %(levelname)s : %(message)s')
logger.setLevel(logging.DEBUG)
consoleHandler = logging.StreamHandler(sys.stderr)
consoleHandler.setLevel(logging.DEBUG)
consoleHandler.setFormatter(formatter)
fileHandler = logging.handlers.RotatingFileHandler(filename="/home/pi/code/ZWOIPCam/error.log",maxBytes=1024000, backupCount=10, mode="a")
fileHandler.setLevel(logging.INFO)
fileHandler.setFormatter(formatter)
logger.addHandler(consoleHandler)
logger.addHandler(fileHandler)

SDK_PATH = 'ASI_linux_mac_SDK_V1.20/lib/armv7/libASICamera2.so'
asi.init(SDK_PATH)


# The worker thread to save the files in the backend
class FileSaver(Thread):
    def __init__(self):
        super(FileSaver, self).__init__()
        self.q = Queue()
        self.start()
    
    def run(self):
        while True:
            img, fn = self.q.get()
            try:
                img.save(fn, 'JPEG', quality=90)
                logger.info('Saved img to {}.'.format(fn))
            except:
                logger.warning('Saving file failed.')
            finally:
                del img


# Checks Internet connection, and will restart the network service if it cannot access a host.
class NetworkChecker(Thread):
    def __init__(self):
        super(NetworkChecker, self).__init__()
        self.last_check_timestamp = 0
        self.error_count = 0
        self.has_tried_networking = False
        self.terminate = False
        # By default, it checks a connection with a timeout of 10 seconds, checks once 30 seconds.
        # So in the case of network connection lost, it will take 400 seconds to respond.
        self.CHECK_TIMEOUT = 10
        self.CHECK_INTERVAL = 30
        self.CHECK_URL = 'https://bing.com/'
        self.MAX_ERROR_COUNT = 10
        self.start()

    def run(self):
        logger.info('Network checker launches.')
        while not self.terminate:
            try:
                if time() < self.last_check_timestamp + self.CHECK_INTERVAL:
                    sleep(0.1)
                    continue
                self.last_check_timestamp = time()
                requests.get(self.CHECK_URL, timeout=self.CHECK_TIMEOUT)
                self.error_count = 0
                self.has_tried_networking = False
                logger.debug('Check {} succeeded.'.format(self.CHECK_URL))
            except Exception as e:
                self.error_count += 1
                logger.error(e)
                logger.error('NetworkChecker error count = {}'.format(self.error_count))
                if self.error_count == 10:
                    if not self.has_tried_networking:
                        # First try to restart the networking service
                        logger.error('About to restart the networking service.')
                        system('service networking restart')
                    else:
                        logger.error("Still failed. About to restart in 60 seconds.")
                        sleep(60)
                        logger.error("About to restart now.")
                        system("reboot now")


# The worker thread that does the heavy lifting
class CameraCapture(Thread):
    def __init__(self, output_stream, latest_stream, interval=0):
        super(CameraCapture, self).__init__()
        self.terminate = False
        self.interval = interval
        self.last_gain = 0
        self.last_exposure = 0
        self.server = None # Optional hook for updating the server
        self.initialize_camera()

        logger.info('Camera initialization complete.')
        self.stream = output_stream
        self.latest_stream = latest_stream
        self.start()

    def initialize_camera(self):
        logger.info('Initializing camera...')
        sleep(2)
        num_cameras = asi.get_num_cameras()
        if num_cameras == 0:
            raise RuntimeError('No ZWO camera was detected.')
        try:
            cameras_found = asi.list_cameras()
            self.camera = asi.Camera(0)
        except Exception as e:
            # When the power is stable, this case is usually not recoverable except restart
            logger.error(e)
            logger.error("About to retry once")
            try:
                self.camera = asi.Camera(0)
            except Exception as e:
                logger.error(e)
                logger.error("Still failed. About to restart in 60 seconds.")
                sleep(60)
                logger.error("About to restart now.")
                system("reboot now")

        camera_info = self.camera.get_camera_property()
        logger.info(camera_info)
        controls = self.camera.get_controls()
        logger.info(controls)

        self.camera.set_image_type(asi.ASI_IMG_RAW8)

        self.camera.set_control_value(asi.ASI_BANDWIDTHOVERLOAD, 
                                self.camera.get_controls()['BandWidth']['DefaultValue'],
                                auto=True)

        # Set auto exposure value
        self.whbi = self.camera.get_roi_format()
        self.camera.auto_wb()
        # Uncomment to enable manual white balance
        # self.camera.set_control_value(asi.ASI_WB_B, 99)
        # self.camera.set_control_value(asi.ASI_WB_R, 75)
        self.camera.set_control_value(asi.ASI_AUTO_MAX_GAIN, 425)
        self.camera.set_control_value(asi.ASI_AUTO_MAX_BRIGHTNESS, 130)
        self.camera.set_control_value(asi.ASI_EXPOSURE,
                                 100000,
                                 auto=True)
        self.camera.set_control_value(asi.ASI_GAIN,
                                 0,
                                 auto=True)
        self.camera.set_control_value(controls['AutoExpMaxExpMS']['ControlType'], 3000)
        # Uncomment to enable flip
        # self.camera.set_control_value(asi.ASI_FLIP, 3)
        self.camera.start_video_capture()

    def run(self):
        logger.info('Start capturing...')
        last_timestamp = 0
        try:
            while not self.terminate:
                if time() < last_timestamp + self.interval:
                    sleep(0.1)
                    continue
                last_timestamp = time()
                #logger.debug('About to take photo.')
                settings = self.camera.get_control_values()
                logger.debug('Gain {gain:d}  Exposure: {exposure:f}'.format(gain=settings['Gain'],
                          exposure=settings['Exposure']))
                self.last_gain = settings['Gain']
                self.last_exposure = settings['Exposure']
                try:
                    img = self.camera.capture_video_frame(timeout=max(1000, 500 + 2 * settings['Exposure'] / 1000))
                    if self.server is not None:
                        self.server.last_update_timestamp = time()
                except Exception as e:
                    logger.error(e)
                    self.camera.stop_exposure()
                    self.camera.stop_video_capture()
                    self.camera.close()
                    self.initialize_camera()
                    # Set the exposure and gain to the last known good value to reduce the auto exposure time
                    self.camera.set_control_value(asi.ASI_EXPOSURE,
                                             self.last_exposure,
                                             auto=True)
                    self.camera.set_control_value(asi.ASI_GAIN,
                                             self.last_gain,
                                             auto=True)
                    continue
                error_count = 0
                # convert the numpy array to PIL image
                mode = None
                if len(img.shape) == 3:
                    img = img[:, :, ::-1]  # Convert BGR to RGB
                if self.whbi[3] == asi.ASI_IMG_RAW16:
                    mode = 'I;16'
                image = Image.fromarray(img, mode=mode)
                # Add some annotation
                draw = ImageDraw.Draw(image)
                pstring = datetime.now().strftime("%m/%d/%Y, %H:%M:%S")
                draw.text((15, 15), pstring, fill='black')
                # Write to the stream
                image.save(self.stream, format='jpeg', quality=90)
                image.save(self.latest_stream, format='jpeg', quality=90)
                # Adaptive auto exposure. 7am-7pm => 120, 7pm-7am => 180.
                # Do this only once in an hour
                now = datetime.now()
                if now.minute == 0 and now.second <= 1:
                    if 7 <= datetime.now().hour <= 18:
                        self.camera.set_control_value(asi.ASI_AUTO_MAX_BRIGHTNESS, 100)
                        # Too bright. Reduce gain and favor longer exposure
                        self.camera.set_control_value(asi.ASI_GAIN,
                                                 0,
                                                 auto=True)
                        self.camera.set_control_value(asi.ASI_EXPOSURE,
                                                 100000,
                                                 auto=True)
                else:
                    self.camera.set_control_value(asi.ASI_AUTO_MAX_BRIGHTNESS, 160)
        finally:
            self.camera.stop_video_capture()
            self.camera.stop_exposure()

if __name__ == '__main__':
    stream_output = StreamingOutput()
    latest_output = StreamingOutput()
    network_checker = NetworkChecker()
    thread = CameraCapture(stream_output, latest_output, 1)
    try:
        address = ('', 8000)
        server = StreamingServer(address, StreamingHandler, stream_output, latest_output)
        thread.server = server
        logger.info('Starting serving...')
        server.serve_forever()
    finally:
        thread.terminate = True
        network_checker.terminate = True
