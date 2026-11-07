"""Sidebar sem Qt: estados, layout, limites, ferramentas, orientação e arrasto."""

import pytest

from desktop.interaction.dwell import DwellTracker, Rect
from desktop.interface.sidebar_model import (
    BUTTONS, Action, Control, Edge, Orientation, SidebarModel, SidebarState, Tool, clamp_avoiding)

W, H = 1920, 1080
MARKERS = [Rect(0, 0, 206, 206), Rect(0, 874, 206, 206), Rect(1714, 874, 206, 206), Rect(1714, 0, 206, 206)]


def model(**kw):
    return SidebarModel(W, H, MARKERS, **kw)


def opened(m, now=0.0):
    m.on_fire(Control.HANDLE, now)
    m.tick(now + 1)
    assert m.state is SidebarState.EXPANDED
    return now + 1


def overlaps(a, b):
    return a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h


def test_starts_collapsed_on_left_middle_with_pointer():
    m = model()
    lay = m.layout(0)
    assert m.state is SidebarState.COLLAPSED and lay.panel is None
    cx, cy = lay.handle.center
    assert cx < 60 and cy == pytest.approx(H / 2)
    assert m.tool is Tool.POINTER
    assert [t.key for t in m.targets(0)] == [Control.HANDLE]


def test_button_size_follows_precision_rule():
    assert model().button == pytest.approx(0.074 * 1080)  # ≈ 80 px


def test_open_animates_and_exposes_all_buttons():
    m = model()
    assert m.on_fire(Control.HANDLE, 10.0) == [{"event": "ui_open"}]
    mid = m.layout(10.05)
    assert m.state is SidebarState.OPENING and 0 < mid.open_fraction < 1
    final_x = m.layout(10.0 + 5).panel  # depois da animação (estado ainda opening até tick)
    m.tick(10.3)
    lay = m.layout(10.3)
    assert m.state is SidebarState.EXPANDED and lay.open_fraction == 1.0
    assert mid.panel.x < lay.panel.x == final_x.x  # deslizou da borda para dentro
    assert [k for k, _ in lay.buttons] == list(BUTTONS)
    assert len(m.targets(10.3)) == 1 + len(BUTTONS)


def test_panel_stays_inside_screen_and_off_markers():
    for orientation in Orientation:
        for edge in Edge:
            for offset in (0.0, 0.2, 0.5, 0.8, 1.0):
                m = model(edge=edge, offset=offset, orientation=orientation)
                now = opened(m)
                lay = m.layout(now)
                p = lay.panel
                assert p.x >= 0 and p.y >= 0 and p.x + p.w <= W and p.y + p.h <= H, (edge, offset)
                assert not any(overlaps(p, mk) for mk in MARKERS), (edge, offset, orientation)
                assert not any(overlaps(lay.handle, mk) for mk in MARKERS), (edge, offset)


def test_select_tool_and_actions():
    m = model()
    now = opened(m)
    assert m.on_fire(Tool.BRUSH, now) == [{"event": "ui_tool", "tool": "brush"}]
    assert m.tool is Tool.BRUSH
    assert m.on_fire(Action.UNDO, now) == [{"event": "ui_action", "action": "undo"}]
    assert m.tool is Tool.BRUSH


def test_buttons_do_nothing_while_collapsed():
    m = model()
    assert m.on_fire(Tool.ERASER, 0) == [] and m.tool is Tool.POINTER


def test_close_keeps_tool_and_orientation():
    m = model()
    now = opened(m)
    m.on_fire(Tool.CIRCLE, now)
    m.on_fire(Control.ORIENTATION, now)
    assert m.on_fire(Control.HANDLE, now) == [{"event": "ui_close"}]
    m.tick(now + 1)
    assert m.state is SidebarState.COLLAPSED
    assert m.tool is Tool.CIRCLE and m.orientation is Orientation.HORIZONTAL


def test_orientation_toggles_grid_shape():
    m = model()
    vw, vh = m.panel_size()
    now = opened(m)
    assert m.on_fire(Control.ORIENTATION, now)[0]["orientation"] == "horizontal"
    hw, hh = m.panel_size()
    assert vh > vw and hw > hh


def test_drag_follows_finger_and_drops_on_nearest_edge():
    m = model()
    now = opened(m)
    grab = m.button_center(Control.MOVE, now)
    assert m.on_fire(Control.MOVE, now, grab) == [{"event": "ui_drag_start"}]
    assert m.targets(now) == []  # nada é acionado durante o arrasto
    # Leva o dedo até perto da borda direita, na altura de 30%, e para.
    events = []
    for i in range(30):
        now += 0.033
        x = grab[0] + (1700 - grab[0]) * min(1, i / 15)
        y = grab[1] + (0.3 * H - grab[1]) * min(1, i / 15)
        events += m.drag_update((x, y), now)
    for _ in range(30):
        now += 0.033
        events += m.drag_update((1700, 0.3 * H), now)
    drops = [e for e in events if e["event"] == "ui_drop"]
    assert len(drops) == 1 and drops[0]["edge"] == "right"
    assert m.state is SidebarState.EXPANDED and m.edge is Edge.RIGHT
    assert m.handle_rect().center[0] > W - 60


def test_drag_drops_when_finger_lost():
    m = model()
    now = opened(m)
    m.on_fire(Control.MOVE, now, m.button_center(Control.MOVE, now))
    assert m.drag_update(None, now + 1.0) == []
    assert m.drag_update(None, now + 1.6)[0]["event"] == "ui_drop"


def test_full_flow_with_dwell_tracker():
    m, dwell = model(), DwellTracker(dwell_s=0.8, tolerance_px=20)
    now, events = 0.0, []

    def hold(point, seconds):
        nonlocal now
        for _ in range(int(seconds / 0.033)):
            now += 0.033
            m.tick(now)
            ev = dwell.update(now, point, m.targets(now))
            if ev and ev.kind == "fire":
                events.extend(m.on_fire(ev.key, now, point))

    hold(m.handle_rect().center, 1.0)
    hold(None, 0.3)
    hold(m.button_center(Tool.ERASER, now), 1.0)
    assert [e["event"] for e in events] == ["ui_open", "ui_tool"] and m.tool is Tool.ERASER


def test_clamp_avoiding_moves_minimally():
    r = clamp_avoiding(Rect(10, 100, 100, 100), W, H, MARKERS)
    assert not any(overlaps(r, mk) for mk in MARKERS)
    assert r.y == pytest.approx(214) and r.x == pytest.approx(10)
