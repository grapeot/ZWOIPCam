from http import server
from streaming import StreamingOutput, StreamingServer, StreamingHandler
from utils import NetworkChecker
import logging
import logging.handlers
import sys

# Set up logging
logger = logging.getLogger(__name__)
formatter = logging.Formatter('%(asctime)s : %(levelname)s : %(message)s')
logger.setLevel(logging.DEBUG)
consoleHandler = logging.StreamHandler(sys.stderr)
consoleHandler.setLevel(logging.DEBUG)
consoleHandler.setFormatter(formatter)
fileHandler = logging.handlers.RotatingFileHandler(filename="/home/pi/code/ZWOIPCam/error.log",maxBytes=10240000, backupCount=10, mode="a")
fileHandler.setLevel(logging.INFO)
fileHandler.setFormatter(formatter)
logger.addHandler(consoleHandler)
logger.addHandler(fileHandler)

if __name__ == '__main__':
    stream_output = StreamingOutput()
    latest_output = StreamingOutput()
    network_checker = NetworkChecker(logger)
    # Uncomment to use the proper camera
    # from RPiCamera import RPiCamera
    # thread = RPiCamera(stream_output, latest_output, logger, 0)
    from ZWOCamera import ZWOCamera
    thread = ZWOCamera(stream_output, latest_output, logger, 0)
    try:
        address = ('', 8000)
        server = StreamingServer(address, StreamingHandler, stream_output, latest_output)
        thread.server = server
        logger.info('Starting serving...')
        server.serve_forever()
    finally:
        thread.terminate = True
        network_checker.terminate = True
