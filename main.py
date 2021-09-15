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
logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
consoleHandler = logging.StreamHandler(sys.stderr)
consoleHandler.setLevel(logging.DEBUG)
fileHandler = logging.handlers.RotatingFileHandler(filename="error.log",maxBytes=1024000, backupCount=10, mode="a")
fileHandler.setLevel(logging.INFO)
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
    def __init__(self, output_stream, latest_stream):
        super(CameraCapture, self).__init__()
        self.terminate = False
        logger.info('Initializing camera...')

        num_cameras = asi.get_num_cameras()
        if num_cameras == 0:
            raise RuntimeError('No ZWO camera was detected.')
        cameras_found = asi.list_cameras()
        camera_id = 0
        self.camera = asi.Camera(camera_id)
        camera_info = self.camera.get_camera_property()
        logger.info(camera_info)
        controls = self.camera.get_controls()

        if camera_info['IsColorCam']:
            self.camera.set_image_type(asi.ASI_IMG_RGB24)
        else:
            self.camera.set_image_type(asi.ASI_IMG_RAW8)

        # Set auto exposure value
        self.whbi = self.camera.get_roi_format()
        self.camera.set_control_value(asi.ASI_WB_B, 99)
        self.camera.set_control_value(asi.ASI_WB_R, 75)
        self.camera.set_control_value(asi.ASI_AUTO_MAX_GAIN, 75)
        self.camera.set_control_value(asi.ASI_AUTO_MAX_BRIGHTNESS, 160)
        self.camera.set_control_value(asi.ASI_EXPOSURE,
                                 controls['Exposure']['DefaultValue'],
                                 auto=True)
        self.camera.set_control_value(asi.ASI_GAIN,
                                 controls['Gain']['DefaultValue'],
                                 auto=True)
        self.camera.set_control_value(controls['AutoExpMaxExpMS']['ControlType'], 20000)
        self.camera.start_video_capture()

        logger.info('Camera initialization complete.')
        self.stream = output_stream
        self.latest_stream = latest_stream
        self.start()

    def run(self):
        logger.info('Start capturing...')
        try:
            while not self.terminate:
                logger.debug('About to take photo.')
                settings = self.camera.get_control_values()
                logger.debug('Gain {gain:d}  Exposure: {exposure:f}'.format(gain=settings['Gain'],
                          exposure=settings['Exposure']))
                try:
                    img = self.camera.capture_video_frame(timeout=500 + 2 * settings['Exposure'])
                except Exception as e:
                    logger.error(e)
                    continue
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
    thread = CameraCapture(stream_output, latest_output)
    try:
        address = ('', 8000)
        server = StreamingServer(address, StreamingHandler, stream_output, latest_output)
        logger.info('Starting serving...')
        server.serve_forever()
    finally:
        thread.terminate = True