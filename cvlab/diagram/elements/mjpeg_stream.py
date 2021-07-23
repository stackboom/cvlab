from .base import *
import io
import logging
import socketserver

from threading import Condition,Thread
from http import server


PAGE = """\
<html>
<head>
<title>mjpeg-video stream</title>
</head>
<body>
<center><img src="stream.jpg" width="1280" height="720"></center>
</body>
</html>
"""

class StreamingOutput(object):
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def write(self, buf):
        # if buf.startswith(b'\xff\xd8'):
        if buf.startswith(b'\xff\xd8') or buf.startswith(b'\x89\x50\x4e\x47'):
            # New frame, copy the existing buffer's content and notify all
            # clients it's available
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)

output = StreamingOutput()

class StreamingHandler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            content = PAGE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/stream.jpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))

        elif self.path == '/stream.png':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/png')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))
        else:
            self.send_error(404)
            self.end_headers()

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    pass


class MjpegStreamServer(NormalElement):
    name = 'Stream Server'
    comment = ''
    package = "Video IO"
    port = 8000
    server = None
    type = 0

    def __init__(self):
        super().__init__()
        pass

    def stop(self):
        videoThread = Thread(target=self.shutdown)
        videoThread.start()
        pass

    def shutdown(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        pass

    def start(self):
        videoThread = Thread(target=self.serve)
        videoThread.start()
        pass

    def serve(self):
        if self.server is None:
            address = ('', self.port)
            self.server = StreamingServer(address, StreamingHandler)
            self.server.serve_forever()
        pass

    def get_attributes(self):
        return [Input('src', 'src'),Input('mask','mask',optional=True)], \
               [Output('dst', 'dst')], \
               [
                   IntParameter('port', 'Listen Port',value=8001,min_=1000,max_=65535),
                   ComboboxParameter('type', name='Image Type',values = [('JPEG',0),('PNG',1)],default_value_idx=0),
                   ButtonParameter('start',self.start),
                   ButtonParameter('stop',self.stop)
               ]

    def process_inputs(self, inputs, outputs, parameters):
        self.port = parameters['port']
        self.type = parameters['type']

        if self.type==1 and inputs['mask'] is not None:
            mask = inputs['mask'].value
            img = cv.cvtColor(inputs['src'].value,cv.COLOR_RGB2RGBA)
            img[mask==0] = [0,0,0,0]
            code_result, buf = cv.imencode('.png', img)
            if code_result:
                output.write(buf.tobytes())
            outputs['dst'] = inputs['src']
        else:
            code_result, buf = cv.imencode('.jpg', inputs['src'].value)
            if code_result:
                output.write(buf.tobytes())
            outputs['dst'] = inputs['src']
        pass

    def __del__(self):

        super(MjpegStreamServer, self).__del__()


register_elements(__name__, [MjpegStreamServer])