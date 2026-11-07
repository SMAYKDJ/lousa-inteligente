"""Escolha da mão quando a câmera vê as duas (lousa vs. braço afastado)."""

from desktop.communication.message_protocol import HandState, Handedness, IndexTip
from desktop.core.hand_selection import HandSelector


def hand(x, y, size, palm_spread=None):
    """Mão com a ponta em (x, y) camera_norm e palma de `size` px."""
    spread = palm_spread if palm_spread is not None else size / 1000
    palm = (IndexTip(x, y + 0.1, 0),) + tuple(
        IndexTip(x + dx * spread, y + 0.1 - spread, 0) for dx in (-1.5, -0.5, 0.5, 1.5))
    return HandState(present=True, handedness=Handedness.RIGHT, confidence=0.9,
                     index_tip=IndexTip(x, y, 0.0), palm=palm, palm_size_px=size)


def identity_surface(p):
    """'Calibração' em que a lousa ocupa a faixa x ∈ [0,25; 0,75] da câmera."""
    return ((p.x - 0.25) / 0.5, p.y)


def test_single_hand_is_used():
    h = hand(0.5, 0.5, 100)
    assert HandSelector().select([h]) is h


def test_no_hands():
    assert HandSelector().select([]) is None


def test_without_calibration_smaller_hand_wins():
    near_board, near_camera = hand(0.3, 0.5, 80), hand(0.7, 0.5, 150)
    assert HandSelector().select([near_camera, near_board]) is near_board


def test_hand_over_the_board_beats_hand_outside():
    # O braço afastado aparece MENOR, mas fora da lousa: a mão sobre a lousa vence.
    on_board, outside = hand(0.5, 0.5, 120), hand(0.9, 0.5, 70)
    assert HandSelector().select([outside, on_board], identity_surface) is on_board


def test_both_on_board_smaller_wins():
    touching, in_front = hand(0.4, 0.5, 80), hand(0.6, 0.5, 140)
    assert HandSelector().select([in_front, touching], identity_surface) is touching


def test_keeps_current_hand_unless_other_is_clearly_better():
    selector = HandSelector()
    a, b = hand(0.4, 0.5, 100), hand(0.6, 0.5, 130)
    assert selector.select([a, b], identity_surface) is a
    # No quadro seguinte "b" fica um pouco menor que "a" (diferença < 20%): mantém "a".
    a2, b2 = hand(0.41, 0.5, 100), hand(0.6, 0.5, 92)
    assert selector.select([b2, a2], identity_surface) is a2
    # "b" fica claramente menor (> 20%): troca.
    a3, b3 = hand(0.42, 0.5, 100), hand(0.6, 0.5, 70)
    assert selector.select([a3, b3], identity_surface) is b3


def test_previous_hand_lost_picks_best_again():
    selector = HandSelector()
    a = hand(0.4, 0.5, 100)
    selector.select([a], identity_surface)
    far_away_new = [hand(0.7, 0.2, 140), hand(0.3, 0.8, 90)]
    assert selector.select(far_away_new, identity_surface) is far_away_new[1]
