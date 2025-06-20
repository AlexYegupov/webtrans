import asyncio
import os
import cv2
import numpy as np
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, MediaStreamTrack
from av import VideoFrame, AudioFrame

pcs = set()

class CameraStreamTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.cap = cv2.VideoCapture(0)

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        ret, frame = self.cap.read()
        if not ret:
            raise Exception("Не удалось прочитать кадр с камеры")
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame

class DummyAudioStreamTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()
        self.sample_rate = 48000
        self.samples_per_frame = 960
        self.channels = 1

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        sine_wave = np.zeros((self.samples_per_frame,), dtype=np.int16)
        frame = AudioFrame.from_ndarray(sine_wave, format="s16", layout="mono")
        frame.pts = pts
        frame.time_base = time_base
        return frame

async def index(request):
    return web.FileResponse(os.path.join("static", "index.html"))

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    # Сначала установить offer от клиента
    await pc.setRemoteDescription(offer)

    # Затем добавить медиа-треки
    pc.addTrack(CameraStreamTrack())
    pc.addTrack(DummyAudioStreamTrack())

    # Создать и установить ответ
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })

async def on_shutdown(app):
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

app = web.Application()
app.on_shutdown.append(on_shutdown)
app.router.add_get("/", index)
app.router.add_post("/offer", offer)
app.router.add_static("/static/", path="static", name="static")

web.run_app(app, port=8081)
