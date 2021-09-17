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
fileHandler = logging.handlers.RotatingFileHandler(filename="/home/pi/code/allsky/error.log",maxBytes=1024000, backupCount=10, mode="a")
fileHandler.setLevel(logging.INFO)
fileHandler.setFormatter(formatter)
logger.addHandler(consoleHandler)
logger.addHandler(fileHandler)

SDK_PATH = 'ASI_linux_mac_SDK_V1.20/lib/armv7/libASICamera2.so'
asi.init(SDK_PATH)


"""The worker thread to save the files in the backend"""
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

"""The worker thread doing the heavy lifting"""
class CameraCapture(Thread):
    def __init__(self, output_stream, latest_stream, interval=0):
        super(CameraCapture, self).__init__()
        self.terminate = False
        self.interval = interval
        self.last_gain = 0
        self.last_exposure = 0
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
        cameras_found = asi.list_cameras()
        camera_id = 0
        self.camera = asi.Camera(camera_id)
        camera_info = self.camera.get_camera_property()
        logger.info(camera_info)
        controls = self.camera.get_controls()
        logger.info(controls)

        if camera_info['IsColorCam']:
            self.camera.set_image_type(asi.ASI_IMG_RGB24)
        else:
            self.camera.set_image_type(asi.ASI_IMG_RAW8)

        self.camera.set_control_value(asi.ASI_BANDWIDTHOVERLOAD, 
                                self.camera.get_controls()['BandWidth']['DefaultValue'],
                                auto=True)

        # Set auto exposure value
        self.whbi = self.camera.get_roi_format()
        self.camera.set_control_value(asi.ASI_WB_B, 99)
        self.camera.set_control_value(asi.ASI_WB_R, 75)
        self.camera.set_control_value(asi.ASI_AUTO_MAX_GAIN, 100)
        self.camera.set_control_value(asi.ASI_AUTO_MAX_BRIGHTNESS, 160)
        self.camera.set_control_value(asi.ASI_EXPOSURE,
                                 controls['Exposure']['DefaultValue'],
                                 auto=True)
        self.camera.set_control_value(asi.ASI_GAIN,
                                 controls['Gain']['DefaultValue'],
                                 auto=True)
        self.camera.set_control_value(controls['AutoExpMaxExpMS']['ControlType'], 3000)
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
                draw.text((15, 15), pstring, fill='white')
                # Write to the stream
                image.save(self.stream, format='jpeg', quality=90)
                image.save(self.latest_stream, format='jpeg', quality=90)
        finally:
            self.camera.stop_video_capture()
            self.camera.stop_exposure()

if __name__ == '__main__':
    stream_output = StreamingOutput()
    latest_output = StreamingOutput()
    thread = CameraCapture(stream_output, latest_output, 1)
    try:
        address = ('', 8000)
        server = StreamingServer(address, StreamingHandler, stream_output, latest_output)
        logger.info('Starting serving...')
        server.serve_forever()
    finally:
        thread.terminate = True
