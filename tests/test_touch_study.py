"""Estudo do toque (etapa 5.3): sequência de etapas, relatório e integração na lousa."""

from __future__ import annotations

import json
import math
import random

import pytest

from desktop import config
from desktop.interaction.touch_study import TouchStudy, build_prompts
from desktop.vision.landmark_recorder import LandmarkRecorder
from desktop.vision.synthetic_hands import HandPose, hand_shape
from tools import touch_report


def run_study(study, t0=100.0, step=0.05, on_frame=None):
    """Roda o estudo até o fim, com uma amostra de mão a cada `step` s. Devolve os eventos."""
    events = study.start(t0)
    t = t0
    while study.active:
        t += step
        study.on_sample(True)
        if on_frame is not None:
            on_frame(t, study)
        events += study.tick(t)
    return events, t


def test_prompts_alternate_touch_and_air_in_three_places():
    prompts = build_prompts(3)
    assert len(prompts) == 15
    assert [p.label for p in prompts[:5]] == ["touch", "air2", "touch", "air2", "air5"]
    assert len({p.spot for p in prompts}) == 3
    # Em cada rodada, encostado e no ar no mesmo lugar e com o mesmo movimento.
    for r in range(3):
        rnd = prompts[5 * r:5 * r + 5]
        assert len({p.spot for p in rnd}) == 1


def test_each_phase_logs_its_recording_window():
    study = TouchStudy()
    events, _ = run_study(study)
    phases = [e for e in events if e["event"] == "touch_phase"]
    assert len(phases) == 15
    for p in phases:
        dur = (p["end_ms"] - p["start_ms"]) / 1000
        assert abs(dur - config.TOUCH_STUDY_RECORD_S) < 0.06
        assert p["hand_frames"] > 50
    # Entre uma gravação e a próxima, o tempo de preparar a mão.
    gap = (phases[1]["start_ms"] - phases[0]["end_ms"]) / 1000
    assert abs(gap - config.TOUCH_STUDY_PREPARE_S) < 0.06
    assert events[-1]["event"] == "touch_study_done"
    assert not study.active


def test_view_goes_prepare_record_summary_and_cancel():
    study = TouchStudy()
    assert study.view(0) is None
    study.start(0.0)
    v = study.view(0.0)
    assert v.kind == "prepare" and v.step == 1 and v.total == 15 and v.motion == "still"
    study.tick(config.TOUCH_STUDY_PREPARE_S + 0.01)
    assert study.view(config.TOUCH_STUDY_PREPARE_S + 0.01).kind == "record"
    assert study.cancel() == [{"event": "touch_study_cancel", "index": 0}]
    assert not study.active and study.cancel() == []


def test_summary_warns_when_the_hand_was_missing():
    study = TouchStudy(build_prompts(1))
    study.start(0.0)
    t = 0.0
    while study.phase != "summary":
        t += 0.1
        study.tick(t)  # nenhuma amostra de mão
    assert any("quase sem a mão" in line for line in study.view(t).lines)


def test_auc():
    assert touch_report.auc([2, 3, 4], [0, 1]) == 1.0
    assert touch_report.auc([0, 1], [2, 3]) == 0.0
    assert touch_report.auc([1, 1], [1, 1]) == 0.5
    assert touch_report.auc([], [1]) is None


# --- relatório de ponta a ponta com mãos sintéticas -----------------------------------

ASPECT = 9 / 16  # câmera em pé (720×1280), como no celular


def _hand(x, y, tip_bend_deg, rng):
    """Mão apontando; `tip_bend_deg` dobra só a última falange (o "achatamento" ao encostar)."""
    shape = hand_shape(HandPose(curl=(0.8, 0.1, 0.9, 0.9, 0.9)))
    p7, p8 = shape[7], shape[8]
    v = tuple(p8[i] - p7[i] for i in range(3))
    a = math.radians(tip_bend_deg)
    # Gira a falange da ponta para a câmera (no plano y-z do dedo).
    vy = v[1] * math.cos(a)
    vz = v[2] - abs(v[1]) * math.sin(a)
    shape[8] = (p7[0] + v[0], p7[1] + vy, p7[2] + vz)
    shape = [tuple(c + rng.gauss(0, 0.012) for c in p) for p in shape]
    palm = (0, 5, 9, 13, 17)
    cx = sum(shape[i][0] for i in palm) / 5
    cy = sum(shape[i][1] for i in palm) / 5
    scale = 0.12
    image = [(x + (lx - cx) * scale / ASPECT, y - (ly - cy) * scale, lz * scale) for lx, ly, lz in shape]
    world = [(lx * 0.09, -ly * 0.09, lz * 0.09) for lx, ly, lz in shape]
    return image, world


def _write_study(tmp_path, bend_touch=30.0):
    rng = random.Random(4)
    rec_path = tmp_path / "landmarks-x.jsonl.gz"
    recorder = LandmarkRecorder(rec_path)
    study = TouchStudy()
    events = []

    def frame(t, st):
        if st.phase != "record":
            return
        p = st.prompts[st.index]
        bend = bend_touch if p.label == "touch" else 0.0
        x = p.spot[0] + (0.05 * math.sin(4 * t) if p.motion == "drag" else 0.0)
        img, wld = _hand(x, p.spot[1], bend + rng.gauss(0, 4), rng)
        recorder.write(int(t * 1000), ASPECT, [(img, wld, "Right")])

    ev, _ = run_study(study, on_frame=frame, step=1 / 24)
    recorder.close()
    ev[0]["recording"] = rec_path.name
    session = tmp_path / "session-x.jsonl"
    session.write_text("\n".join(json.dumps(e) for e in ev) + "\n", encoding="utf-8")
    return session, rec_path


def test_report_finds_the_signal_that_separates_touch(tmp_path, capsys):
    session, rec = _write_study(tmp_path)
    result = touch_report.analyze(session, rec)
    res = result["comparisons"]["air2/todos"]
    assert res["dobra_ponta"]["useful"] and res["dobra_ponta"]["touch_is"] == "maior"
    assert res["dobra_ponta"]["rounds_agree"] == res["dobra_ponta"]["rounds"] == 6
    assert not res["dobra_meio"]["useful"]  # a outra articulação não muda
    assert touch_report.main([str(session)]) == 0
    out = capsys.readouterr().out
    assert "dobra_ponta" in out and "promissor" in out and "Conclusão: separam" in out


def test_report_says_so_when_nothing_separates(tmp_path, capsys):
    session, rec = _write_study(tmp_path, bend_touch=0.0)
    assert touch_report.main([str(session), str(rec)]) == 0
    assert "nenhum sinal separa" in capsys.readouterr().out


def test_report_without_study(tmp_path, capsys):
    session = tmp_path / "session-y.jsonl"
    session.write_text('{"event": "start"}\n', encoding="utf-8")
    assert touch_report.main([str(session)]) == 1


# --- integração na lousa --------------------------------------------------------------

def test_window_t_starts_study_turns_on_recording_and_esc_cancels(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication
    from desktop.interface.cursor_window import CursorWindow
    from desktop.interface.qt_bridge import QtServerBridge

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(config, "RECORD_LANDMARKS_PATH", None)
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    log = []
    clock = [50.0]
    window = CursorWindow(QtServerBridge(), "https://x/?token=t", clock=lambda: clock[0],
                          event_log=lambda event, **f: log.append((event, f)))
    window.resize(1200, 600)
    window.show()

    def press(key):
        window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))

    press(Qt.Key.Key_T)
    assert window.touch.active
    assert config.RECORD_LANDMARKS_PATH is not None and config.RECORD_LANDMARKS_PATH.startswith(str(tmp_path))
    start = [f for e, f in log if e == "touch_study_start"][0]
    assert start["recording"].startswith("landmarks-")
    assert not window.grab().isNull()  # etapa "prepare"
    clock[0] += config.TOUCH_STUDY_PREPARE_S + 0.1
    window._calibration_tick()
    assert window.touch.phase == "record"
    assert not window.grab().isNull()
    clock[0] += config.TOUCH_STUDY_RECORD_S + 0.1
    window._calibration_tick()
    assert any(e == "touch_phase" for e, _ in log)
    press(Qt.Key.Key_Escape)
    assert not window.touch.active
    assert any(e == "touch_study_cancel" for e, _ in log)
    window.close()
    window.deleteLater()
    app.processEvents()
