"""Precisão: correção dos 9 pontos, filtro One Euro e malha virtual."""

import math
import random

import pytest

from desktop import config
from desktop.calibration.residual import AXIS, ResidualCorrection
from desktop.core.one_euro import OneEuro, OneEuro2D

GRID = [(x, y) for y in AXIS for x in AXIS]


def bias(x, y):
    """Erro sistemático que cresce para as bordas (como lente/paralaxe)."""
    return 0.03 * (x - 0.5), 0.02 * (y - 0.5) + 0.01 * (x - 0.5)


def test_zero_correction_is_identity():
    c = ResidualCorrection.zero()
    assert c.apply(0.3, 0.7) == (0.3, 0.7) and c.max_offset() == 0


def test_correction_is_exact_at_the_nine_points():
    errors = [bias(x, y) for x, y in GRID]
    c = ResidualCorrection.from_errors(errors)
    for (x, y), (dx, dy) in zip(GRID, errors):
        cx, cy = c.apply(x + dx, y + dy)
        # offset é interpolado no ponto medido (não no alvo): erro de 2ª ordem
        assert math.hypot(cx - x, cy - y) < 0.002


def test_correction_reduces_error_between_points():
    c = ResidualCorrection.from_errors([bias(x, y) for x, y in GRID])
    random.seed(3)
    before = after = 0.0
    for _ in range(200):
        x, y = random.uniform(0.05, 0.95), random.uniform(0.05, 0.95)
        dx, dy = bias(x, y)
        before += math.hypot(dx, dy)
        cx, cy = c.apply(x + dx, y + dy)
        after += math.hypot(cx - x, cy - y)
    assert after < 0.15 * before


def test_correction_accumulates_over_g_runs():
    errors = [bias(x, y) for x, y in GRID]
    first = ResidualCorrection.from_errors(errors)
    second = ResidualCorrection.from_errors([(0.0, 0.0)] * 9, previous=first)
    assert second == first  # sem erro restante: a correção não muda
    half = ResidualCorrection.from_errors([(e[0] / 2, e[1] / 2) for e in errors])
    full = ResidualCorrection.from_errors([(e[0] / 2, e[1] / 2) for e in errors], previous=half)
    assert all(math.isclose(a[0], b[0]) and math.isclose(a[1], b[1])
               for ra, rb in zip(full.offsets, first.offsets) for a, b in zip(ra, rb))


def test_bad_measurements_are_rejected():
    errors = [(0.0, 0.0)] * 8 + [(config.RESIDUAL_MAX_ERROR * 2, 0.0)]
    with pytest.raises(ValueError):
        ResidualCorrection.from_errors(errors)
    with pytest.raises(ValueError):
        ResidualCorrection.from_errors([(0.0, 0.0)] * 8 + [(float("nan"), 0.0)])
    with pytest.raises(ValueError):
        ResidualCorrection.from_errors([(0.0, 0.0)] * 4)


def test_one_euro_reduces_jitter_and_follows_motion():
    random.seed(1)
    f = OneEuro()
    out = [f(0.5 + random.gauss(0, 0.002), i / 30) for i in range(300)]
    jitter = (sum((o - 0.5) ** 2 for o in out[30:]) / 270) ** 0.5
    assert jitter < 0.5 * 0.002
    f = OneEuro()
    lag = [0.2 + 0.5 * i / 30 - f(0.2 + 0.5 * i / 30, i / 30) for i in range(60)]
    assert max(lag[20:]) < 0.01  # escrita a 0,5/s: atraso < 1% da tela


def test_one_euro_2d_reset_and_repeated_timestamp():
    f = OneEuro2D()
    assert f(0.1, 0.2, 1.0) == (0.1, 0.2)
    x, y = f(0.3, 0.4, 1.0)  # mesmo instante: intervalo mínimo de 1 ms, não reinicia (como no kit)
    assert 0.1 < x < 0.3 and 0.2 < y < 0.4
    f.reset()
    assert f(0.9, 0.9, 2.0) == (0.9, 0.9)


def test_one_euro_2d_diagonal_stays_straight():
    """Velocidade vetorial: num movimento diagonal os dois eixos andam juntos."""
    f = OneEuro2D()
    for i in range(30):
        x, y = f(0.2 + 0.02 * i, 0.2 + 0.005 * i, i / 30)
    # a razão dy/dx da posição filtrada é a da reta (1:4)
    assert abs((y - 0.2) / (x - 0.2) - 0.25) < 0.01


def test_one_euro_long_gap_is_clamped():
    f = OneEuro()
    f(0.0, 0.0)
    assert f(1.0, 10.0) < 1.0  # 10 s parado conta como 100 ms: não salta direto


def test_grid_coords():
    pytest.importorskip("PySide6")
    from desktop.interface.grid_view import grid_coords, grid_rows
    assert grid_rows(1920, 1080) == 11
    assert grid_coords(960, 540, 1920, 1080) == (10.0, 5.5)
