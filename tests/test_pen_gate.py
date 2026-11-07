"""Estados da caneta e da interface (Fase 5)."""

from desktop.interaction.pen_gate import GateState, PenGate
from desktop.interaction.pen_state import PenState


def run(gate, frames, drawing_tool=True):
    return [gate.update(pen, ui, True, drawing_tool) for pen, ui in frames]


def test_down_on_board_draws_and_blocks_ui_until_up():
    g = PenGate()
    r = run(g, [(False, False), (True, False), (True, True), (True, False), (False, False)])
    assert [x.pen for x in r] == [False, True, True, True, False]
    assert [x.dwell for x in r] == [True, False, False, False, True]
    assert r[1].started and r[4].ended and g.state is GateState.UP


def test_down_on_ui_then_board_is_blocked():
    g = PenGate()
    r = run(g, [(True, True), (True, False), (True, False)])
    assert [x.pen for x in r] == [False, False, False]
    assert all(x.dwell for x in r) and g.state is GateState.BLOCKED
    r = run(g, [(False, False), (True, False)])
    assert r[1].pen and r[1].started


def test_pointer_tool_never_captures():
    g = PenGate()
    r = run(g, [(True, False), (True, True)], drawing_tool=False)
    assert g.state is GateState.ON_UI and r[0].dwell and not r[0].started


def test_no_point_does_not_start_drawing():
    g = PenGate()
    assert not g.update(True, False, False, True).started and g.state is GateState.POINTING


def test_ambiguous_pose_keeps_pen_down_with_legacy_engine():
    p = PenState(down_frames=2, up_frames=3, hold_on_other=True)
    for pose in ["pointing", "pointing"]:
        p.update(pose)
    assert p.down
    for _ in range(10):
        p.update("other")
    assert p.down  # pose ambígua não levanta
    for _ in range(3):
        p.update("open")
    assert not p.down


def test_ambiguous_pose_does_not_put_pen_down():
    p = PenState(down_frames=2, up_frames=3)
    for _ in range(5):
        p.update("other")
    assert not p.down


def test_with_new_engine_ambiguous_pose_lifts_pen():
    """Teste real 2026-11-07 13:59: com o reconhecimento novo a caneta ficava presa por até 63 s."""
    p = PenState(down_frames=2, up_frames=3, hold_on_other=False)
    for _ in range(2):
        p.update("pointing")
    assert p.down
    for _ in range(3):
        p.update("other")
    assert not p.down
