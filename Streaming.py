from time import sleep, time
from io import BytesIO
from datetime import datetime
from os.path import join, exists
from os import mkdir
from threading import Condition, Thread
from http import server
import socketserver
import json
import logging


class StreamingOutput(object):
    def __init__(self):
        self.frame = None
        self.buffer = BytesIO()
        self.condition = Condition()

    def write(self, buf):
        if buf.startswith(b'\xff\xd8'):
            # New frame, copy the existing buffer's content and notify all
            # clients it's available
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, handler, output_stream, latest_stream):
        super(StreamingServer, self).__init__(address, handler)
        self.output_stream = output_stream
        self.latest_stream = latest_stream
        # Used for invokers to know the camera has stopped responding
        self.last_update_timestamp = time()

class StreamingHandler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/stream.mjpg')
            self.end_headers()
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with self.server.output_stream.condition:
                        self.server.output_stream.condition.wait()
                        frame = self.server.output_stream.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))
        elif self.path == '/latest.jpg' or self.path == '/latest_full.jpg':
            if self.server.last_update_timestamp is not None and time() > self.server.last_update_timestamp + 20:
                # hasn't been updated in 20 seconds, begin returning 404
                self.send_error(404)
                self.end_headers()
            else:
                self.send_response(200)
                self.send_header('Age', 0)
                self.send_header('Cache-Control', 'no-cache, private')
                self.send_header('Pragma', 'no-cache')
                frame = self.server.latest_stream.frame
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', len(frame))
                self.end_headers()
                self.wfile.write(frame)
        else:
            self.send_error(404)
            self.end_headers()
