from fractions import Fraction
from picamera import PiCamera
from threading import Condition, Thread
from os import system
from io import BytesIO
from time import sleep, time
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont


# The worker thread that does the heavy lifting
# Thsi sis fro Raspberry Pi's camera
class RPiCamera(Thread):
    def __init__(self, output_stream, latest_stream, logger, interval=0):
        super(RPiCamera, self).__init__()
        self.terminate = False
        self.interval = interval
        self.server = None # Optional hook for updating the watchdog, which monitors when the last frame was updated
        self.logger = logger
        self.initialize_camera()

        self.logger.info('Camera initialization complete.')
        self.stream = output_stream
        self.latest_stream = latest_stream
        self.start()

    def initialize_camera(self):
        self.logger.info('Initializing camera...')
        resolution = (1640, 1232)
        try:
            self.camera = PiCamera()
            self.camera.resolution = resolution
            self.camera.framerate_range = (Fraction(1, 10), Fraction(15, 1))
            self.camera.start_preview()
        except Exception as e:
            # When the power is stable, this case is usually not recoverable except restart
            self.logger.error(e)
            self.logger.error("About to retry once")
            try:
                self.camera = PiCamera()
                self.camera.resolution = resolution
                self.camera.framerate_range = (Fraction(1, 10), Fraction(15, 1))
                self.camera.start_preview()
            except Exception as e:
                self.logger.error(e)
                self.logger.error("Still failed. About to restart in 60 seconds.")
                sleep(60)
                self.logger.error("About to restart now.")
                system("reboot now")
        self.camera.awb_mode = 'auto'
        self.camera.exposure_mode = 'night'
        self.camera.shutter_speed = 0 # auto exposure
        # Uncomment to enable flips
        self.camera.hflip = True
        self.camera.vflip = True
        sleep(2)

    def run(self):
        self.logger.info('Start capturing...')
        last_timestamp = 0
        buff = BytesIO()
        try:
            while not self.terminate:
                if time() < last_timestamp + self.interval:
                    sleep(0.1)
                    continue
                last_timestamp = time()
                self.logger.debug('Gain {gain_n:d}/{gain_d:d}  Exposure: {exposure:f}'.format(
                    gain_n=self.camera.analog_gain.numerator,
                    gain_d=self.camera.analog_gain.denominator,
                    exposure=self.camera.exposure_speed))
                try:
                    buff.seek(0)
                    self.camera.capture(buff, format='jpeg', quality=90)
                    if self.server is not None:
                        self.server.last_update_timestamp = time()
                except Exception as e:
                    self.logger.error(e)
                    self.camera.close()
                    self.initialize_camera()
                    continue
                buff.seek(0)
                image = Image.open(buff)
                # Add some annotation
                draw = ImageDraw.Draw(image)
                pstring = datetime.now().strftime("%m/%d/%Y, %H:%M:%S")
                draw.text((15, 15), pstring, fill='black')
                # Write to the stream
                image.save(self.stream, format='jpeg', quality=90)
                image.save(self.latest_stream, format='jpeg', quality=90)
        finally:
            self.camera.close()
