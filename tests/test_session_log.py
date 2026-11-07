"""Testes do log de sessão e do resumo (medição sem anotação manual)."""

import json

from desktop.communication.message_protocol import ProtocolError, ErrorCode, parse_message
from desktop.communication.server import ConnectionState, ServerEvents
from desktop.core.session_log import FanOutEvents, SessionLog
from tools.log_summary import format_table, read_segments


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def msg(obj):
    return parse_message(json.dumps(obj))


HELLO = {"type": "hello", "v": 0, "client": "mobile-web", "client_version": "0.2.0",
         "camera": {"width": 720, "height": 1280, "facing": "environment"}}


def status(fps, state="tracking_active", inference=None, delegate="GPU", load=None):
    m = {"type": "status", "v": 0, "fps": fps, "tracking_state": state, "delegate": delegate}
    if inference is not None:
        m["inference_ms"] = inference
    if load is not None:
        m["load_ms"] = load
    return msg(m)


def tracking(seq, present=True):
    hand = ({"present": True, "handedness": "Right", "confidence": 0.9,
             "index_tip": {"x": 0.5, "y": 0.5, "z": 0.0}} if present else {"present": False})
    return msg({"type": "hand_tracking", "v": 0, "seq": seq, "t_client_ms": 1.0, "hand": hand})


def records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_writes_one_json_line_per_event(tmp_path):
    log = SessionLog(tmp_path / "s.jsonl", clock=FakeClock())
    log.write("start", ip="1.2.3.4")
    log.on_connection_state(ConnectionState.CONNECTED, "x")
    log.on_hello(msg(HELLO))
    log.on_status(status(8.5, inference=98.0, load=14800))
    log.on_rtt(12.345)
    log.on_invalid_message(ProtocolError(ErrorCode.INVALID_MESSAGE, "teste"))
    log.close()
    events = [r["event"] for r in records(tmp_path / "s.jsonl")]
    assert events == ["start", "connection", "hello", "status", "rtt", "invalid", "stop"]
    status_rec = records(tmp_path / "s.jsonl")[3]
    assert status_rec["inference_ms"] == 98.0 and status_rec["delegate"] == "GPU"
    assert records(tmp_path / "s.jsonl")[4]["rtt_ms"] == 12.35


def test_hand_tracking_is_summarized_per_second(tmp_path):
    clock = FakeClock()
    log = SessionLog(tmp_path / "s.jsonl", clock=clock)
    for seq in range(1, 31):  # 30 mensagens em ~1 s, 20 com mão
        log.on_hand_tracking(tracking(seq, present=seq <= 20))
        clock.now += 1 / 30
    log.on_hand_tracking(tracking(31))
    log.close()
    rates = [r for r in records(tmp_path / "s.jsonl") if r["event"] == "tracking_rate"]
    assert sum(r["msgs"] for r in rates) == 31
    assert sum(r["with_hand"] for r in rates) == 21
    assert len(rates) <= 2  # resumido, não uma linha por mensagem


def test_fan_out_reaches_all_listeners():
    class Recorder(ServerEvents):
        def __init__(self):
            self.rtts = []

        def on_rtt(self, rtt_ms):
            self.rtts.append(rtt_ms)

    a, b = Recorder(), Recorder()
    FanOutEvents(a, b).on_rtt(5.0)
    assert a.rtts == b.rtts == [5.0]


def test_summary_groups_by_connection_and_uses_hand_frames_only(tmp_path):
    clock = FakeClock()
    log = SessionLog(tmp_path / "s.jsonl", clock=clock)
    # Variante 1: GPU 720×1280
    log.on_connection_state(ConnectionState.CONNECTED, "a")
    log.on_hello(msg(HELLO))
    log.on_status(status(0, state="initializing", delegate="GPU"))
    for fps in (8.0, 8.5, 9.0):
        log.on_status(status(fps, inference=98.0, load=14800))
    log.on_status(status(10.0, state="tracking_lost", load=14800))  # sem mão: fora da mediana c/ mão
    log.on_rtt(10.0)
    log.on_connection_state(ConnectionState.DISCONNECTED, "client_closed")
    # Variante 2: CPU 480×640
    hello2 = dict(HELLO, camera={"width": 480, "height": 640, "facing": "environment"})
    log.on_connection_state(ConnectionState.CONNECTED, "b")
    log.on_hello(msg(hello2))
    for fps in (20.0, 22.0):
        log.on_status(status(fps, inference=40.0, delegate="CPU", load=3000))
    log.close()

    segments = read_segments(tmp_path / "s.jsonl")
    assert [s.camera for s in segments] == ["720×1280", "480×640"]
    first, second = segments
    assert first.delegate == "GPU" and first.load_ms == 14800
    assert first.fps_hand == [8.0, 8.5, 9.0] and first.with_hand == 3
    assert first.end_reason == "client_closed"
    assert second.delegate == "CPU" and second.fps_hand == [20.0, 22.0]

    table = format_table(segments)
    assert "| 720×1280 | GPU | 14.8 s | 8.5 | 98 |" in table
    assert "| 480×640 | CPU | 3.0 s | 21.0 | 40 |" in table


def test_stream_mode_summary(tmp_path):
    from desktop.vision.frame_processor import VisionState, VisionStats
    from tools.log_summary import format_report

    clock = FakeClock()
    log = SessionLog(tmp_path / "s.jsonl", clock=clock)
    log.on_vision_state(VisionState.READY, "1900 ms")
    log.on_connection_state(ConnectionState.CONNECTED, "a")
    log.on_hello(msg(HELLO))
    for fps in (24.0, 26.0):
        log.on_status(msg({"type": "status", "v": 0, "fps": fps, "tracking_state": "inactive",
                           "mode": "stream", "encode_ms": 9.0, "frame_kb": 40.0, "skipped": 2}))
        log.on_vision_stats(VisionStats(
            window_s=1.0, received=25, processed=20, dropped=5, decode_errors=0, fps=20.0,
            decode_ms=1.5, inference_ms=30.0, wait_ms=0.5, frame_kb=40.0, width=360,
            height=640, with_hand=15))
    log.on_connection_state(ConnectionState.DISCONNECTED, "client_closed")
    log.close()

    (segment,) = read_segments(tmp_path / "s.jsonl")
    assert segment.mode == "stream" and segment.skipped == 4
    assert (segment.received, segment.processed, segment.dropped) == (50, 40, 10)
    report = format_report([segment])
    assert "Modo stream" in report and "Modo local" not in report
    assert "| 360×640 | 25.0 | 40 | 9 (main) | 4 | 20.0 | 30 | 0.5 | 10/50 | 75% | 0% | — | — (±—) |" in report

    lines = (tmp_path / "s.jsonl").read_text().splitlines()
    assert any('"event": "vision_state"' in line and '"ready"' in line for line in lines)


def test_marker_summary(tmp_path):
    from desktop.core.coordinate_mapper import CameraNormPoint as P
    from tools.log_summary import marker_summary

    log = SessionLog(tmp_path / "s.jsonl", clock=FakeClock())
    square = [P(0.1, 0.1), P(0.15, 0.1), P(0.15, 0.2), P(0.1, 0.2)]
    for _ in range(4):
        log.on_markers({0: square, 1: square}, 640, 360)
    log.on_markers({0: square}, 640, 360)
    from desktop.vision.frame_processor import VisionStats
    log.on_vision_stats(VisionStats(1.0, 5, 5, 0, 0, 5.0, 1.0, 10.0, 0.1, 10.0, 640, 360, 5))
    log.write("marker_reference", ok=True, seen=[0, 1])
    log.write("camera_moved", shift=0.034, seen=[0, 1])
    log.close()
    text = marker_summary(tmp_path / "s.jsonl")
    assert "5 verificações" in text and "id 0: 100%" in text and "id 1: 80%" in text
    assert "id 2: 0%" in text and "referência: ok" in text and "máx 3.4%" in text


def test_drawing_summary(tmp_path):
    from tools.log_summary import drawing_summary
    log = tmp_path / "s.jsonl"
    log.write_text('{"event":"ui_tool","tool":"brush"}\n{"event":"draw_stroke","points":40}\n'
                   '{"event":"draw_shape","shape":"circle"}\n{"event":"ui_confirm","answer":"yes"}\n')
    text = drawing_summary(log)
    assert "traços 1" in text and "círculos 1" in text and "limpar: sim 1" in text and "brush" in text


def test_pen_summary(tmp_path):
    from tools.log_summary import pen_summary
    log = tmp_path / "s.jsonl"
    log.write_text('{"event":"pen_up","held_s":0.1,"pose":"open"}\n{"event":"pen_up","held_s":2.0,"pose":"open"}\n'
                   '{"event":"pen_up","held_s":1.0,"pose":"sem_mao"}\n')
    text = pen_summary(log)
    assert "desceu 3 vezes" in text and "1 vezes por menos de 0,3 s" in text and "open 2" in text
    assert "indicador" in text


def test_gesture_comparison_summary(tmp_path):
    from tools.log_summary import gesture_comparison
    log = tmp_path / "s.jsonl"
    log.write_text('{"event":"start","gesture_engine":"kit"}\n'
                   '{"event":"vision","pose_flips":3,"pose_alt_flips":42,"one_hand":1800,"processed":1800,"window_s":60.0}\n')
    text = gesture_comparison(log)
    assert "novo (kit) trocou de pose 3 vezes" in text and "antigo 42 vezes" in text


def test_summary_counts_motions(tmp_path):
    from tools.log_summary import drawing_summary
    log = tmp_path / "s.jsonl"
    log.write_text('{"event":"motion_swipe","direction":"left"}\n{"event":"motion_click","key":"eraser"}\n'
                   '{"event":"draw_zoom","scale":1.5}\n')
    text = drawing_summary(log)
    assert "deslizes 1" in text and "cliques por pinça 1" in text and "zoom com duas mãos 1" in text
