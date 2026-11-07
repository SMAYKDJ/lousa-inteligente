"""Laboratório de gestos (tecla L): acerto, reação e confusões, novo × antigo."""

from desktop import config
from desktop.interaction.gesture_lab import GestureLab

PROMPTS = (("pointing", "Aponte", ""), ("pinch", "Pinça", ""))


def run_prompt(lab, t0, poses, alt_poses, gaps=None, fps=30):
    n = int(config.LAB_PROMPT_S * fps)
    events = []
    for i in range(n):
        t = t0 + i / fps
        lab.on_sample(t, poses(t - t0), alt_poses(t - t0), (gaps or (lambda _: 0.9))(t - t0))
        events += lab.tick(t)
    return events + lab.tick(t0 + config.LAB_PROMPT_S + 0.01)


def test_scores_hits_reaction_and_confusions():
    lab = GestureLab(PROMPTS)
    lab.start(0.0)
    # novo: aponta a partir de 0,5 s; antigo: pisca entre apontar e "other"
    ev = run_prompt(lab, 0.0, lambda dt: "pointing" if dt > 0.5 else "open",
                    lambda dt: "pointing" if dt > 0.5 and int(dt * 30) % 3 else "other")
    r = ev[0]
    assert r["event"] == "lab_prompt" and r["target"] == "pointing"
    assert r["novo"]["hit"] == 1.0 and abs(r["novo"]["reaction_s"] - 0.5) < 0.05
    assert 0.6 < r["antigo"]["hit"] < 0.7 and r["antigo"]["confusions"] == {"other": r["antigo"]["confusions"]["other"]}
    assert lab.index == 1 and lab.view(config.LAB_PROMPT_S + 0.1).step == 2


def test_pinch_uses_gap_and_only_new():
    lab = GestureLab(PROMPTS)
    lab.start(0.0)
    run_prompt(lab, 0.0, lambda dt: "pointing", lambda dt: "pointing")
    t1 = config.LAB_PROMPT_S + 0.01
    ev = run_prompt(lab, t1, lambda dt: "other", lambda dt: "other", gaps=lambda dt: 0.1 if dt > 0.4 else 0.9)
    pinch = next(e for e in ev if e["event"] == "lab_prompt")
    assert pinch["target"] == "pinch" and pinch["novo"]["hit"] == 1.0 and "antigo" not in pinch
    done = next(e for e in ev if e["event"] == "lab_done")
    assert len(done["results"]) == 2
    view = lab.view(t1 + config.LAB_PROMPT_S + 0.1)
    assert view.kind == "summary" and view.lines[0].startswith("Apontar: novo 100%")
    assert view.lines[1].startswith("Pinça: novo 100%") and "antigo" not in view.lines[1]


def test_live_feedback_and_cancel():
    lab = GestureLab(PROMPTS)
    lab.start(0.0)
    lab.on_sample(0.1, "pointing", "pointing", 0.9)
    assert "✓" in lab.view(0.2).text
    lab.on_sample(0.2, "fist", "fist", 0.9)
    assert "Mão fechada" in lab.view(0.3).text and "✓" not in lab.view(0.3).text
    assert lab.cancel()[0]["event"] == "lab_cancel" and not lab.active
