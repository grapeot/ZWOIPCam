from threading import Condition, Thread
from os import system
from time import sleep, time
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import zwoasi as asi

# Set this according to your device
SDK_PATH = 'ASI_linux_mac_SDK_V1.20.1/lib/armv6/libASICamera2.so'
asi.init(SDK_PATH)


# The worker thread that does the heavy lifting
class ZWOCamera(Thread):
    def __init__(self, output_stream, latest_stream, logger, interval=0):
        super(ZWOCamera, self).__init__()
        self.terminate = False
        self.interval = interval
        self.last_gain = 0
        self.last_exposure = 0
        self.server = None # Optional hook for updating the watchdog, which monitors when the last frame was updated
        self.logger = logger
        self.initialize_camera()

        self.logger.info('Camera initialization complete.')
        self.stream = output_stream
        self.latest_stream = latest_stream
        self.start()

    def initialize_camera(self):
        self.logger.info('Initializing camera...')
        sleep(2)
        num_cameras = asi.get_num_cameras()
        if num_cameras == 0:
            raise RuntimeError('No ZWO camera was detected.')
        try:
            cameras_found = asi.list_cameras()
            self.camera = asi.Camera(0)
        except Exception as e:
            # When the power is stable, this case is usually not recoverable except restart
            self.logger.error(e)
            self.logger.error("About to retry once")
            try:
                self.camera = asi.Camera(0)
            except Exception as e:
                self.logger.error(e)
                self.logger.error("Still failed. About to restart in 60 seconds.")
                sleep(60)
                self.logger.error("About to restart now.")
                system("reboot now")

        camera_info = self.camera.get_camera_property()
        self.logger.info(camera_info)
        controls = self.camera.get_controls()
        self.logger.info(controls)

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
        self.logger.info('Start capturing...')
        last_timestamp = 0
        try:
            while not self.terminate:
                if time() < last_timestamp + self.interval:
                    sleep(0.1)
                    continue
                last_timestamp = time()
                # self.logger.debug('About to take photo.')
                settings = self.camera.get_control_values()
                self.logger.debug('Gain {gain:d}  Exposure: {exposure:f}'.format(gain=settings['Gain'],
                          exposure=settings['Exposure']))
                self.last_gain = settings['Gain']
                self.last_exposure = settings['Exposure']
                try:
                    img = self.camera.capture_video_frame(timeout=max(1000, 500 + 2 * settings['Exposure'] / 1000))
                    if self.server is not None:
                        self.server.last_update_timestamp = time()
                except Exception as e:
                    self.logger.error(e)
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
                # convert the numpy array to PIL image
                mode = None
                if len(img.shape) == 3:
                    img = img[:, :, ::-1]  # Convert BGR to RGB
                if self.whbi[3] == asi.ASI_IMG_RAW16:
                    mode = 'I;16'
                image = Image.fromarray(img, mode=mode)
                # Add some annotation
                draw = ImageDraw.Draw(image)
                pstring = datetime.now().strftime("%m/%d/%Y, %H:%M:%S") + f', gain {self.last_gain}, exp {self.last_exposure}'
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
