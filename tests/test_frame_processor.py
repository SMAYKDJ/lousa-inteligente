"""Testes do processador de quadros (D013) com detector e decodificador falsos.

O MediaPipe real é coberto em test_hand_tracker.py (pulado se não instalado).
"""

import threading
import time
from types import SimpleNamespace

import pytest

from desktop.communication.frame_protocol import FrameMessage
from desktop.communication.message_protocol import HandState, IndexTip, Handedness
from desktop.communication.server import ConnectionState
from desktop.vision.frame_processor import FrameProcessor, VisionEvents, VisionState

HAND = HandState(present=True, handedness=Handedness.RIGHT, confidence=0.9,
                 index_tip=IndexTip(0.25, 0.75, 0.0))


def frame(seq: int, jpeg: bytes = b"\xff\xd8ok") -> FrameMessage:
    return FrameMessage(seq=seq, t_client_ms=float(seq), jpeg=jpeg)


def fake_decode(jpeg: bytes):
    if jpeg.endswith(b"bad"):
        return None
    return SimpleNamespace(shape=(360, 640, 3))


class FakeDetector:
    def __init__(self, gate: threading.Event | None = None) -> None:
        self.gate = gate
        self.timestamps: list[int] = []
        self.closed = False

    def detect(self, rgb, timestamp_ms):
        self.timestamps.append(timestamp_ms)
        if self.gate is not None:
            self.gate.wait(2)
        return HAND

    def close(self):
        self.closed = True


class Recorder(VisionEvents):
    def __init__(self) -> None:
        self.tracking = []
        self.states = []
        self.stats = []

    def on_hand_tracking(self, message):
        self.tracking.append(message)

    def on_vision_state(self, state, detail):
        self.states.append((state, detail))

    def on_vision_stats(self, stats):
        self.stats.append(stats)


def wait_for(cond, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return
        time.sleep(0.005)
    raise AssertionError("condição não atingida")


@pytest.fixture
def make():
    created = []

    def _make(detector=None, interval=0.05, clock=time.monotonic):
        det = detector or FakeDetector()
        out = Recorder()
        proc = FrameProcessor(lambda: det, out, fake_decode, clock=clock, stats_interval_s=interval)
        proc.start()
        created.append(proc)
        wait_for(lambda: (VisionState.READY in [s for s, _ in out.states]))
        return proc, out, det

    yield _make
    for proc in created:
        proc.stop()


def test_frame_becomes_hand_tracking(make):
    proc, out, det = make()
    proc.on_frame(frame(7))
    wait_for(lambda: out.tracking)
    msg = out.tracking[0]
    assert (msg.seq, msg.t_client_ms, msg.hand) == (7, 7.0, HAND)
    assert msg.inference_ms is not None


def test_only_latest_frame_waits(make):
    gate = threading.Event()
    proc, out, det = make(FakeDetector(gate))
    proc.on_frame(frame(1))
    wait_for(lambda: det.timestamps)  # 1 está no detector, travado
    for seq in (2, 3, 4):
        proc.on_frame(frame(seq))
    gate.set()
    wait_for(lambda: len(out.tracking) == 2)
    assert [m.seq for m in out.tracking] == [1, 4]
    wait_for(lambda: sum(s.dropped for s in out.stats) == 2)
    assert sum(s.received for s in out.stats) == 4
    assert sum(s.processed for s in out.stats) == 2


def test_decode_error_is_counted_not_fatal(make):
    proc, out, det = make()
    proc.on_frame(frame(1, b"\xff\xd8bad"))
    wait_for(lambda: sum(s.decode_errors for s in out.stats) == 1)
    proc.on_frame(frame(2))
    wait_for(lambda: [m.seq for m in out.tracking] == [2])


def test_stats_have_sizes_and_rates(make):
    proc, out, det = make()
    proc.on_frame(frame(1))
    wait_for(lambda: any(s.processed for s in out.stats))
    stats = next(s for s in out.stats if s.processed)
    assert (stats.width, stats.height) == (640, 360)
    assert stats.with_hand == 1 and stats.fps > 0
    assert stats.frame_kb is not None and stats.inference_ms is not None


def test_timestamps_strictly_increase_with_frozen_clock(make):
    proc, out, det = make(clock=lambda: 100.0)
    for seq in (1, 2, 3):
        proc.on_frame(frame(seq))
        wait_for(lambda s=seq: len(out.tracking) and out.tracking[-1].seq == s)
    assert det.timestamps == sorted(set(det.timestamps))
    assert len(det.timestamps) == 3


def test_disconnect_discards_pending_frame(make):
    gate = threading.Event()
    proc, out, det = make(FakeDetector(gate))
    proc.on_frame(frame(1))
    wait_for(lambda: det.timestamps)
    proc.on_frame(frame(2))
    proc.on_connection_state(ConnectionState.DISCONNECTED, "client_closed")
    gate.set()
    wait_for(lambda: len(out.tracking) == 1)
    time.sleep(0.05)
    assert [m.seq for m in out.tracking] == [1]


def test_detector_failure_becomes_error_state():
    out = Recorder()

    def broken():
        raise RuntimeError("sem modelo")

    proc = FrameProcessor(broken, out, fake_decode)
    proc.start()
    wait_for(lambda: any(s is VisionState.ERROR for s, _ in out.states))
    assert "sem modelo" in out.states[-1][1]
    proc.stop()


def test_stop_closes_detector(make):
    proc, out, det = make()
    proc.stop()
    assert det.closed


def test_latency_from_capture_time(make):
    proc, out, det = make()
    now_ms = time.monotonic() * 1000
    proc.on_frame(FrameMessage(seq=1, t_client_ms=1.0, jpeg=b"\xff\xd8ok",
                               received_ms=now_ms - 5, capture_ms=now_ms - 40))
    wait_for(lambda: any(s.to_result_ms is not None for s in out.stats))
    stats = next(s for s in out.stats if s.to_result_ms is not None)
    assert stats.to_arrival_ms == pytest.approx(35, abs=1)
    assert stats.to_result_ms >= 40


def test_no_latency_without_capture_time(make):
    proc, out, det = make()
    proc.on_frame(frame(1))
    wait_for(lambda: any(s.processed for s in out.stats))
    assert all(s.to_result_ms is None for s in out.stats)


def test_latest_preview_keeps_only_last_frame_and_clears_on_disconnect(make):
    proc, out, det = make()
    assert proc.latest_preview() is None
    proc.on_frame(frame(1))
    wait_for(lambda: proc.latest_preview() is not None)
    rgb, hand = proc.latest_preview()
    assert rgb.shape == (360, 640, 3) and hand == HAND
    proc.on_connection_state(ConnectionState.DISCONNECTED, "client_closed")
    assert proc.latest_preview() is None
