"""Percebe o celular mexido com os marcadores escondidos (D030).

Com os marcadores fora da tela (D028), a compensação de movimento não tem o
que ver. Este módulo compara cada quadro (reduzido, em tons de cinza) com uma
foto de referência tirada no momento em que os marcadores somem, por
correlação de fase (`cv2.phaseCorrelate`): um deslocamento que se mantém indica
que a câmera, e não o que está na frente dela, mudou de lugar.

- A área da lousa (onde o slide e as anotações mudam) é excluída quando o
  resto da cena tem textura suficiente; senão, usa-se a imagem toda.
- A referência e as medidas ficam só na memória, numa imagem de 160 px:
  nada é gravado nem enviado (CLAUDE.md §11).

Quem decide o que fazer com a medida é a janela (cursor_window.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from desktop import config


@dataclass(frozen=True)
class SceneShift:
    dx: float  # fração da largura da imagem
    dy: float  # fração da altura
    response: float  # nitidez do pico da correlação (0..1): baixa = medida pouco confiável

    @property
    def magnitude(self) -> float:
        return float(np.hypot(self.dx, self.dy))


def small_gray(rgb: Any, width: int = config.SCENE_MOTION_WIDTH) -> np.ndarray:
    import cv2
    h, w = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY) if rgb.ndim == 3 else rgb
    return cv2.resize(gray, (width, max(8, round(width * h / w))), interpolation=cv2.INTER_AREA).astype(np.float32)


class SceneMotion:
    def __init__(self) -> None:
        self._ref: np.ndarray | None = None
        self._weight: np.ndarray | None = None
        self.used_whole_frame = False

    @property
    def has_reference(self) -> bool:
        return self._ref is not None

    def clear(self) -> None:
        self._ref = self._weight = None

    def set_reference(self, small: np.ndarray, surface_quad: Sequence[tuple[float, float]] | None) -> None:
        """`surface_quad`: cantos da lousa na câmera (camera_norm), para excluí-la; None = imagem toda."""
        import cv2
        h, w = small.shape
        mask = np.ones((h, w), np.float32)
        self.used_whole_frame = True
        if surface_quad is not None:
            quad = np.array(surface_quad, np.float64)
            center = quad.mean(axis=0)
            grown = center + (quad - center) * (1 + config.SCENE_MASK_MARGIN)
            poly = np.round(grown * [w, h]).astype(np.int32)
            outside = mask.copy()
            cv2.fillPoly(outside, [poly], 0.0)
            gy, gx = np.gradient(small)
            texture = np.hypot(gx, gy)
            # Só exclui a lousa se o que sobra tem área e textura para medir.
            if (outside.mean() >= config.SCENE_MIN_MASK
                    and float((texture * outside).sum() / max(outside.sum(), 1)) >= config.SCENE_MIN_TEXTURE):
                mask, self.used_whole_frame = outside, False
        mask = cv2.GaussianBlur(mask, (0, 0), 2.0)
        self._weight = mask * cv2.createHanningWindow((w, h), cv2.CV_32F)
        self._ref = self._prep(small)

    def _prep(self, small: np.ndarray) -> np.ndarray:
        wsum = float(self._weight.sum()) or 1.0
        mean = float((small * self._weight).sum() / wsum)
        return ((small - mean) * self._weight).astype(np.float32)

    def measure(self, small: np.ndarray) -> SceneShift | None:
        import cv2
        if self._ref is None or small.shape != self._ref.shape:
            return None
        (dx, dy), response = cv2.phaseCorrelate(self._ref, self._prep(small))
        h, w = small.shape
        return SceneShift(dx / w, dy / h, float(response))
