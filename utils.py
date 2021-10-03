from threading import Thread
from os import system
from time import sleep, time
from queue import Queue
import requests


# The worker thread to save the files in the backend
class FileSaver(Thread):
    def __init__(self, logger):
        super(FileSaver, self).__init__()
        self.q = Queue()
        self.logger = logger
        self.start()
   
    def run(self):
        while True:
            img, fn = self.q.get()
            try:
                img.save(fn, 'JPEG', quality=90)
                self.logger.info('Saved img to {}.'.format(fn))
            except:
                self.logger.warning('Saving file failed.')
            finally:
                del img


# Checks Internet connection, and will restart the network service if it cannot access a host.
class NetworkChecker(Thread):
    def __init__(self, logger):
        super(NetworkChecker, self).__init__()
        self.last_check_timestamp = 0
        self.error_count = 0
        self.has_tried_networking = False
        self.terminate = False
        self.logger = logger
        # By default, it checks a connection with a timeout of 10 seconds, checks once 30 seconds.
        # So in the case of network connection lost, it will take 400 seconds to respond.
        self.CHECK_TIMEOUT = 10
        self.CHECK_INTERVAL = 30
        self.CHECK_URL = 'https://bing.com/'
        self.MAX_ERROR_COUNT = 10
        self.start()

    def run(self):
        self.logger.info('Network checker launches.')
        while not self.terminate:
            try:
                if time() < self.last_check_timestamp + self.CHECK_INTERVAL:
                    sleep(0.1)
                    continue
                self.last_check_timestamp = time()
                requests.get(self.CHECK_URL, timeout=self.CHECK_TIMEOUT)
                self.error_count = 0
                self.has_tried_networking = False
                self.logger.debug('Check {} succeeded.'.format(self.CHECK_URL))
            except Exception as e:
                self.error_count += 1
                self.logger.error(e)
                self.logger.error('NetworkChecker error count = {}'.format(self.error_count))
                if self.error_count == 10:
                    if not self.has_tried_networking:
                        # First try to restart the networking service
                        self.logger.error('About to restart the networking service.')
                        system('service networking restart')
                    else:
                        self.logger.error("Still failed. About to restart in 60 seconds.")
                        sleep(60)
                        self.logger.error("About to restart now.")
                        system("reboot now")
