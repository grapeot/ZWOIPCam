from picamera import PiCamera
from time import sleep, time
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from fractions import Fraction
from os.path import join, exists
from os import mkdir, system
from threading import Condition, Thread
from http import server
from streaming import StreamingOutput, StreamingServer, StreamingHandler
from copy import deepcopy
from sys import exit
from utils import NetworkChecker
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
from ZWOCamera import ZWOCamera

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

if __name__ == '__main__':
    stream_output = StreamingOutput()
    latest_output = StreamingOutput()
    network_checker = NetworkChecker(logger)
    thread = ZWOCamera(stream_output, latest_output, logger, 1)
    try:
        address = ('', 8000)
        server = StreamingServer(address, StreamingHandler, stream_output, latest_output)
        thread.server = server
        logger.info('Starting serving...')
        server.serve_forever()
    finally:
        thread.terminate = True
        network_checker.terminate = True
