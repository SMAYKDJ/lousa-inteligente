"""Testes do mapeamento provisório camera_norm → ui_px (etapa 1.3)."""

import pytest

from desktop.core.coordinate_mapper import CameraNormPoint, StretchMapper, UiPoint, UiSize

UI = UiSize(1280, 720)


@pytest.mark.parametrize(
    "camera, expected",
    [
        (CameraNormPoint(0.0, 0.0), UiPoint(0.0, 0.0)),        # canto superior esquerdo
        (CameraNormPoint(1.0, 1.0), UiPoint(1280.0, 720.0)),   # canto inferior direito
        (CameraNormPoint(0.5, 0.5), UiPoint(640.0, 360.0)),    # centro
        (CameraNormPoint(0.25, 0.75), UiPoint(320.0, 540.0)),
    ],
)
def test_stretch_maps_frame_onto_window(camera, expected):
    assert StretchMapper().map(camera, UI) == expected


def test_axes_are_not_swapped_or_mirrored():
    # x da câmera cresce para a direita da tela; y cresce para baixo.
    mapper = StretchMapper()
    left, right = mapper.map(CameraNormPoint(0.1, 0.5), UI), mapper.map(CameraNormPoint(0.9, 0.5), UI)
    top, bottom = mapper.map(CameraNormPoint(0.5, 0.1), UI), mapper.map(CameraNormPoint(0.5, 0.9), UI)
    assert left.x < right.x and left.y == right.y
    assert top.y < bottom.y and top.x == bottom.x


def test_values_outside_frame_are_clamped_to_window():
    # Defesa extra: o protocolo já rejeita valores fora de [0, 1].
    assert StretchMapper().map(CameraNormPoint(-0.2, 1.4), UI) == UiPoint(0.0, 720.0)


def test_follows_window_size():
    point = CameraNormPoint(0.5, 0.5)
    assert StretchMapper().map(point, UiSize(1920, 1080)) == UiPoint(960.0, 540.0)
