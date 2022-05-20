from threading import Condition, Thread
from os import system
from time import sleep, time
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageStat
from AutoExposure import AutoExposurer
import numpy as np
import zwoasi as asi

# Set this according to your device
SDK_PATH = 'ASI_linux_mac_SDK_V1.20/lib/armv7/libASICamera2.so'
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
        self.continuousFailureCount = 0
        self.maxContinuousFailureCount = 5
        self.initialize_camera()

        # auto stretch
        self.auto_stretch = True
        self.auto_stretch_threshold = 40
        self.auto_stretch_target = 150

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

        # Uncomment to use binning
        #self.camera.set_roi(bins=4)
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
        # Uncomment to use stock auto exposure
        #self.useStockAutoExposure = True
        #self.camera.set_control_value(asi.ASI_AUTO_MAX_GAIN, 425)
        #self.camera.set_control_value(asi.ASI_AUTO_MAX_BRIGHTNESS, 130)
        #self.camera.set_control_value(controls['AutoExpMaxExpMS']['ControlType'], 3000)
        # Use our own auto exposure
        self.useStockAutoExposure = False
        maxGain = controls['Gain']['MaxValue']
        self.autoExposurer = AutoExposurer(maxGain, 500000) # us
        self.camera.set_control_value(asi.ASI_EXPOSURE,
                                 1000,
                                 auto=self.useStockAutoExposure)
        self.camera.set_control_value(asi.ASI_GAIN,
                                 0,
                                 auto=self.useStockAutoExposure)
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
                self.last_gain = settings['Gain']
                self.last_exposure = settings['Exposure']
                try:
                    img = self.camera.capture_video_frame(timeout=max(5000, 500 + 10 * settings['Exposure'] / 1000))
                    if self.server is not None:
                        self.server.last_update_timestamp = time()
                except Exception as e:
                    self.logger.error(e)
                    self.continuousFailureCount += 1
                    if self.continuousFailureCount >= self.maxContinuousFailureCount:
                        self.logger.error("Max continuous failure count reached.. About to restart in 60 seconds.")
                        sleep(60)
                        self.logger.error("About to restart now.")
                        system("reboot now")
                    self.camera.stop_exposure()
                    self.camera.stop_video_capture()
                    self.camera.close()
                    self.initialize_camera()
                    # Set the exposure and gain to the last known good value to reduce the auto exposure time
                    self.camera.set_control_value(asi.ASI_EXPOSURE,
                                             self.last_exposure,
                                             auto=self.useStockAutoExposure)
                    self.camera.set_control_value(asi.ASI_GAIN,
                                             self.last_gain,
                                             auto=self.useStockAutoExposure)
                    continue
                self.continuousFailureCount = 0
                # Update the auto exposure
                result = self.autoExposurer.adjustExp(self.last_gain, self.last_exposure, img)
                if result is None:
                    # For unknown reason, sometimes the result would be None. Simply retry would solve the issue
                    result = self.autoExposurer.adjustExp(self.last_gain, self.last_exposure, img)
                    if result is None:
                        continue
                changed, newGain, newExp, med = result
                if changed:
                    self.camera.set_control_value(asi.ASI_EXPOSURE,
                        newExp,
                        auto=self.useStockAutoExposure)
                    self.camera.set_control_value(asi.ASI_GAIN,
                        newGain,
                        auto=self.useStockAutoExposure)
                    self.logger.debug(f'Changed {changed} Med: {med} Gain: {newGain} Exposure: {newExp}')
                else:
                    self.logger.debug(f'Changed {changed} Med: {med} Gain: {self.last_gain} Exposure: {self.last_exposure}')
                # convert the numpy array to PIL image
                mode = None
                if len(img.shape) == 3:
                    img = img[:, :, ::-1]  # Convert BGR to RGB
                if self.whbi[3] == asi.ASI_IMG_RAW16:
                    mode = 'I;16'
                image = Image.fromarray(img, mode=mode)
                # If the image is too dark, auto stretch it
                stat = ImageStat.Stat(image)
                mean = stat.mean[0]
                if self.auto_stretch and mean < self.auto_stretch_threshold:
                    # apply a gamma transform
                    gamma = np.log(self.auto_stretch_target) / np.log(mean)
                    arr = np.asarray(image)
                    arr = np.minimum(255, np.power(arr, gamma)).astype('uint8')
                    image = Image.fromarray(arr, mode=image.mode)
                # Add some annotation
                draw = ImageDraw.Draw(image)
                pstring = datetime.now().strftime("%m/%d/%Y, %H:%M:%S") + f', gain {self.last_gain}, exp {self.last_exposure}'
                draw.text((15, 15), pstring, fill='white')
                # Write to the stream
                image.save(self.stream, format='jpeg', quality=90)
                image.save(self.latest_stream, format='jpeg', quality=90)
        finally:
            self.camera.stop_video_capture()
            self.camera.stop_exposure()
