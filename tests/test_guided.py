"""Assistente de calibração: etapas em ordem, uma de cada vez."""

from desktop import config
from desktop.calibration.guided import GuidedSetup


def test_steps_in_order_with_intro_and_summary():
    g = GuidedSetup()
    g.start(0.0)
    assert g.view(1.0).kind == "intro" and g.view(1.0).step == 1
    assert g.tick(1.0) is None  # o cartão ainda está na tela
    t = config.GUIDED_INTRO_S
    assert g.tick(t) == "corners" and g.phase == "running"
    assert g.tick(t + 1) is None  # não inicia nada enquanto a etapa roda
    g.step_done("corners", {"error_px": 7.0}, t + 40)
    assert g.view(t + 41).step == 2
    t2 = t + 40 + config.GUIDED_INTRO_S
    assert g.tick(t2) == "verify_before"
    g.step_done("verify_before", {"median_px": 20.0}, t2 + 30)
    t3 = t2 + 30 + config.GUIDED_INTRO_S
    assert g.tick(t3) == "grid"
    g.step_done("grid", {"median_px": 18.0, "correction": "aplicada"}, t3 + 70)
    t4 = t3 + 70 + config.GUIDED_INTRO_S
    assert g.tick(t4) == "verify_after"
    events = g.step_done("verify_after", {"median_px": 8.0}, t4 + 30)
    assert events[-1]["event"] == "guided_done" and events[-1]["improvement_pct"] == 60
    v = g.view(t4 + 31)
    assert v.kind == "summary" and any("Melhora: 60%" in line for line in v.lines)
    g.tick(t4 + 30 + config.GUIDED_SUMMARY_S)
    assert not g.active


def test_out_of_order_results_are_ignored_and_cancel():
    g = GuidedSetup()
    g.start(0.0)
    assert g.step_done("grid", {}, 1.0) == []  # teste avulso durante o cartão: não avança
    g.tick(config.GUIDED_INTRO_S)
    assert g.step_done("verify_before", {}, 6.0) == []  # etapa errada
    assert g.cancel() == [{"event": "guided_cancel", "step": "corners"}] and not g.active


def test_worse_after_correction_is_flagged():
    g = GuidedSetup()
    g.results = {"verify_before": {"median_px": 10.0}, "verify_after": {"median_px": 15.0},
                 "grid": {"correction": "aplicada"}}
    g.phase = "summary"
    g.until = 100.0
    lines = g.view(0.0).lines
    assert any("piorou 50%" in line and "desligada" in line for line in lines)
