#! /home/pi/dogcam/env/bin/python3
"""
DogCam!
"""
import os
import io
import time
import bisect
import glob
import asyncio
from functools import partial
import numpy as np
import picamera
from aiohttp import web
from aiohttp.web_runner import AppRunner, TCPSite
import cv2

ROOT = os.path.dirname(__file__)



# TODO:
#  * Add Save only when image changes or every minute
#  * Add web url to retrieve image by date
#  - Slider to look into past and button to go current/pause
#  - Add web url to get motion times
#  - Add label for hours with motion shown


# ===============================
#  Web server
#
def main(framerate=5, resolution='640x480', port=8000, minrate=5, maxrate=5*60):
    loop = asyncio.get_event_loop()

    with picamera.PiCamera(resolution=resolution, framerate=framerate) as cam:
        imgstream = ImageStream(cam, loop)
        motion = MotionCapture(imgstream, loop)
        imgsaver = ImageSaver(imgstream, motion, minrate, maxrate, loop)
        server = WebServer(imgstream, motion, imgsaver, port)

        imgsaver.erase_all()

        loop.run_until_complete(
            asyncio.gather(
                imgstream.run(),
                server.run(),
                motion.run(),
                imgsaver.run(),
                imgsaver.cull(),
            )
        )

    loop.close()


async def onfail(future, callback):
    try:
        await future
    except: #Exception:
        callback()


class ImageSaver:
    def __init__(self, imgstream, motion, minrate, maxrate, loop):
        self.imgstream = imgstream
        self.motion = motion
        self.minrate = minrate
        self.maxrate = maxrate
        self.loop = loop

        self.timestamps = []
        self.history = []
        self.callbacks = {}

    async def run(self):
        lastsave = None
        while True:
            now = time.time()
            jpgdata = await self.imgstream.next()
            if (self.motion.inmotion or lastsave is None
                or abs(lastsave - now) > self.maxrate):

                with open(self.fname(now), 'wb') as fh:
                    fh.write(jpgdata)

                self.timestamps.append(now)

                lastsave = time.time()

                # Save record
                self.history.append((now, self.motion.inmotion))
                for key, callback in self.callbacks.items():
                    self.loop.create_task(
                        onfail(callback(self.history[-1]),
                               partial(self.onsave_clear, key))
                    )

            await asyncio.sleep(self.minrate)

    async def cull(self, rate=60, limit=1*3600*60):
        while True:
            now = time.time()
            cullidx = bisect.bisect(self.timestamps, now - limit)
            for timestamp in self.timestamps[:cullidx]:
                os.remove(self.fname(timestamp))

            self.timestamps = self.timestamps[cullidx:]
            self.history = self.history[cullidx:]

            await asyncio.sleep(rate)

    def get(self, timestamp):
        idx = bisect.bisect_right(self.timestamps, timestamp) - 1
        options = []
        for jdx in [idx, idx+1]:
            try:
                options.append(self.timestamps[jdx])
            except IndexError:
                pass

        best = min(options, key=lambda x: abs(x - timestamp))

        with open(self.fname(best), 'rb') as fh:
            return fh.read()

    def fname(self, timestamp):
        return 'imgs/{}.jpg'.format(timestamp)

    def erase_all(self):
        for filename in glob.glob('imgs/*.jpg'):
            os.remove(filename)

    def onsave(self, callback):
        token = hash(callback)
        self.callbacks[token] = callback
        return token

    def onsave_clear(self, token):
        del self.callbacks[token]



# ====================================
#  Web Server
#
class WebServer:
    def __init__(self, imgstream, motion, imgsaver, port=8000):
        self.port = port
        self.imgstream = imgstream
        self.motion = motion
        self.imgsaver = imgsaver

        self.app = web.Application()
        self.app.router.add_get('/', self.handle_file)
        self.app.router.add_get('/vstream.mjpg', self.handle_stream)
        self.app.router.add_get('/imgs/{timestamp}.jpg', self.handle_img)
        self.app.router.add_get('/motion', self.handle_motion)
        self.app.router.add_get('/history', self.handle_history)
        self.app.router.add_get('/{file}', self.handle_file)

    async def run(self):
        runner = AppRunner(self.app, handle_signals=True)
        await runner.setup()
        site = TCPSite(runner, port=self.port, shutdown_timeout=60.0)
        await site.start()

    async def handle_file(self, request):
        filename = request.match_info.get('file', 'index-video.html')

        src = os.path.join(ROOT, 'web', filename)

        if not os.path.exists(src):
            raise web.HTTPNotFound

        if src.endswith('.js'):
            content_type = 'text/js'
        elif src.endswith('.html'):
            content_type = 'text/html'
        elif src.endswith('.css'):
            content_type = 'text/css'
        else:
            content_type = 'text/plain'

        with open(src, 'r') as fh:
            return web.Response(body=fh.read(), content_type=content_type)

    async def handle_img(self, request):
        try:
            tstamp = float(request.match_info['timestamp'])
        except ValueError:
            raise web.HTTPNotFound

        return web.Response(body=self.imgsaver.get(tstamp),
                            content_type='image/jpeg')

    async def handle_stream(self, request):
        response = web.StreamResponse()
        response.content_type = 'multipart/x-mixed-replace; boundary=--jpegboundary'
        await response.prepare(request)

        def fmt(bytestr):
            return bytes(
                '--jpegboundary\r\n'
                'Content-Type: image/jpeg\r\n'
                'Content-Length: {}\r\n\r\n'.format(len(bytestr)),
                'utf-8'
            ) + bytestr + b'\r\n'

        await response.write(fmt(self.imgstream.latest()))

        while True:
            img = await self.imgstream.next()
            await response.write(fmt(img))

        await response.write_eof()
        return response

    async def handle_motion(self, request):
        response = web.WebSocketResponse()
        await response.prepare(request)
        handle = self.motion.ondetect(response.send_json)

        async for msg in response:
            print(msg)

        self.motion.ondetect_clear(handle)
        await response.close()
        return response

    async def handle_history(self, request):
        response = web.WebSocketResponse()
        await response.prepare(request)

        async def send(record):
            await response.send_json({
                'now': time.time(),
                'records': [record],
            })

        await response.send_json({
            'now': time.time(),
            'records': self.imgsaver.history
        })

        handle = self.imgsaver.onsave(send)

        async for msg in response:
            print(msg)

        self.imgsaver.onsave_clear(handle)
        await response.close()
        return response



# ===================================
#  Image capture
#
class ImageStream:
    def __init__(self, camera, loop):
        self.camera = camera
        self.loop = loop

        self.stream = io.BytesIO()
        self.latest_img = b''

        self.futures = []
        #asyncio.Future()

    async def run(self):
        iterator = self.camera.capture_continuous(self.stream, 'jpeg',
                                                  use_video_port=True)

        while True:
            # Get next image
            value = await self.loop.run_in_executor(None, next, iterator, None)
            if value is None:
                break

            # Grab from stream
            self.stream.seek(0)
            self.latest_img = self.stream.read()
            self.stream.seek(0)
            self.stream.truncate()

            # Set future and reset
            #futures = len(self.futures)
            for future in self.futures:
                if not future.cancelled():
                    future.set_result(self.latest_img)

            self.futures = []

    def latest(self):
        return self.latest_img

    def next(self):
        future = asyncio.Future()
        self.futures.append(future)
        return future




# ===================================
#  Motion Capture
#
class MotionCapture:
    def __init__(self, imgstream, loop):
    #    self.motion_avg = motion_avg
        self.motion_avg = None
        self.imgstream = imgstream
        self.loop = loop
        self.callbacks = {}
        self.inmotion = False

    # === Interface ===
    async def run(self):
        while True:
            jpgdata = await self.imgstream.next()
            motion_data = await self.loop.run_in_executor(
                None, self.process, jpgdata
            )

            for key, callback in self.callbacks.items():
                self.loop.create_task(
                    onfail(callback(motion_data),
                           partial(self.ondetect_clear, key))
                )

            self.inmotion = (len(motion_data) > 0)

            await asyncio.sleep(1)

    def ondetect(self, callback):
        token = hash(callback)
        self.callbacks[token] = callback
        return token

    def ondetect_clear(self, token):
        del self.callbacks[token]

    # === Motion Detection ===
    def process(self, jpgdata):
        if self.motion_avg is None:
            self.init_motion(jpgdata)
            return []
        else:
            return self.detect_motion(jpgdata)

    def detect_motion(self, jpgdata):
        """
        Find motion in the JPG data

        Args:
            jpgdata (bytes): Image data

        Returns:
            [(int, int, int, int)] - Bounding rectangles of motion
        """
        # Image data
        img = self.simplify(jpgdata)
        cv2.accumulateWeighted(img, self.motion_avg, 0.5)
        delta = cv2.absdiff(img, cv2.convertScaleAbs(self.motion_avg))
        delta = cv2.threshold(delta, 5, 255, cv2.THRESH_BINARY)[1]
        delta = cv2.dilate(delta, None, iterations=2)
        contours = cv2.findContours(delta.copy(), cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)[1]
        contours = [cnt for cnt in contours if cv2.contourArea(cnt) > 500]

        return [cv2.boundingRect(cnt) for cnt in contours]

    def simplify(self, jpgdata):
        """
        Reduce image by blurring changing to black and white

        Args:
            jpgdata (bytes): Image Data

        Returns:
            bytes
        """
        img = cv2.imdecode(np.fromstring(jpgdata, np.uint8), cv2.IMREAD_COLOR)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img = cv2.GaussianBlur(img, (21, 21), 0)
        return img

    def init_motion(self, jpgdata):
        """
        Initialize motion detection

        Args:
            jpgdata (bytes): Image Data

        Returns:
            []
        """
        img = self.simplify(jpgdata)
        self.motion_avg = img.astype('float')
        return []





# ==================================
#  Main Interface
#
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Webstream for DogCam')
    parser.add_argument('-f', '--framerate', default=5, type=int,
                        help='Frame rate (Frames per second)')
    parser.add_argument('-p', '--port', default=8000, type=int,
                        help='Port on which to serve web data')
    parser.add_argument('-r', '--resolution', default='640x480')
    args = parser.parse_args()

    main(args.framerate, args.resolution, args.port)
