"""Acionar por permanência (Fase 3)."""

from desktop.interaction.dwell import DwellTracker, Rect, Target

A = Target("a", Rect(0, 0, 80, 80))
B = Target("b", Rect(100, 0, 80, 80))


def feed(tracker, points, start=0.0, step=0.05):
    events, now = [], start
    for p in points:
        now += step
        e = tracker.update(now, p, [A, B])
        if e:
            events.append(e)
    return events, now


def test_fires_after_dwell_time():
    t = DwellTracker(dwell_s=0.8)
    events, _ = feed(t, [(40, 40)] * 20)  # 1 s
    assert [(e.kind, e.key) for e in events] == [("fire", "a")]


def test_does_not_fire_before_time():
    t = DwellTracker(dwell_s=0.8)
    events, now = feed(t, [(40, 40)] * 14)  # 0,7 s
    assert events == [] and 0.8 < t.progress(now) < 1.0


def test_fires_once_until_finger_leaves():
    t = DwellTracker(dwell_s=0.8)
    events, _ = feed(t, [(40, 40)] * 60)  # 3 s parado
    assert len(events) == 1
    events, _ = feed(t, [None] + [(40, 40)] * 20, start=3.0)
    assert [e.kind for e in events] == ["fire"]


def test_small_wobble_outside_is_tolerated():
    t = DwellTracker(dwell_s=0.8, tolerance_px=10)
    pts = [(40, 40), (85, 40), (40, 40), (88, 40)] * 5  # sai até 8 px
    events, _ = feed(t, pts)
    assert [(e.kind, e.key) for e in events] == [("fire", "a")]


def test_leaving_cancels_and_reports_progress():
    t = DwellTracker(dwell_s=0.8)
    events, _ = feed(t, [(40, 40)] * 10 + [(500, 500)])
    assert [(e.kind, e.key) for e in events] == [("cancel", "a")]
    assert 0.5 < events[0].progress < 0.75


def test_quick_pass_over_button_is_not_reported():
    t = DwellTracker(dwell_s=0.8)
    events, _ = feed(t, [(40, 40)] * 2 + [(140, 40)] * 2 + [(500, 500)])
    assert events == []


def test_moving_to_other_button_restarts():
    t = DwellTracker(dwell_s=0.8)
    events, _ = feed(t, [(40, 40)] * 10 + [(140, 40)] * 20)
    assert [(e.kind, e.key) for e in events] == [("cancel", "a"), ("fire", "b")]
