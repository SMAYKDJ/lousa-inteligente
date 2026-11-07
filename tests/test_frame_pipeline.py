"""Integração (D013): quadro JPEG pelo WebSocket → servidor → MediaPipe → rastreamento.

Usa o mesmo build_pipeline do desktop.main e o MediaPipe real (pulado se
não instalado). Imagem real de mão, mas não de sala de aula (CLAUDE.md §9.4).
"""

import asyncio
import json
from pathlib import Path

import pytest

from desktop.communication.frame_protocol import build_frame
from desktop.communication.server import ServerEvents, ServerSettings, create_app
from desktop.core.session_log import SessionLog
from desktop.main import build_pipeline
from desktop.vision.frame_processor import VisionEvents, VisionState

pytest.importorskip("mediapipe")

FIXTURE = Path(__file__).parent / "fixtures" / "hand_thumbs_up.jpg"
TOKEN = "t"
HELLO = {"type": "hello", "v": 0, "client": "mobile-web", "client_version": "0.3.0",
         "camera": {"width": 640, "height": 427, "facing": "environment"}}


class Listener(ServerEvents, VisionEvents):
    def __init__(self):
        self.tracking, self.states, self.stats = [], [], []

    def on_hand_tracking(self, message):
        self.tracking.append(message)

    def on_vision_state(self, state, detail):
        self.states.append(state)

    def on_vision_stats(self, stats):
        self.stats.append(stats)


async def until(cond, timeout=10.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not cond():
        if loop.time() > end:
            raise AssertionError("tempo esgotado")
        await asyncio.sleep(0.02)


async def test_jpeg_frames_become_hand_tracking(aiohttp_client, tmp_path):
    listener = Listener()
    session_log = SessionLog(tmp_path / "s.jsonl")
    events, processor = build_pipeline(listener, session_log)
    processor.start()
    try:
        client = await aiohttp_client(create_app(ServerSettings(token=TOKEN), events))
        await until(lambda: VisionState.READY in listener.states, timeout=30)

        ws = await client.ws_connect(f"/ws?token={TOKEN}")
        await ws.send_str(json.dumps(HELLO))
        assert (await ws.receive_json(timeout=2))["type"] == "welcome"

        jpeg = FIXTURE.read_bytes()
        for seq in range(1, 21):
            await ws.send_bytes(build_frame(seq, 1000.0 + seq * 33, jpeg))
            await asyncio.sleep(0.033)
        await until(lambda: listener.tracking and listener.tracking[-1].seq == 20)
        await until(lambda: listener.stats)

        assert all(m.hand.present for m in listener.tracking)
        assert [m.seq for m in listener.tracking] == sorted(m.seq for m in listener.tracking)
        stats = listener.stats[-1]
        assert (stats.width, stats.height) == (640, 427)
        await ws.close()
    finally:
        processor.stop()
        session_log.close()

    lines = [json.loads(line) for line in (tmp_path / "s.jsonl").read_text().splitlines()]
    kinds = {line["event"] for line in lines}
    assert {"vision_state", "vision", "tracking_rate"} <= kinds
    assert not any("jpeg" in line or "image" in line for line in lines)  # nunca grava imagem
