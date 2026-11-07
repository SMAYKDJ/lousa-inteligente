"""Calibração guardada para a próxima aula (D034).

Guarda a conversão câmera → lousa e onde os 4 marcadores apareceram na
câmera naquele momento. Na abertura seguinte, se os marcadores estão no mesmo
lugar (o celular não mudou de posição) e a tela tem o mesmo tamanho, a
calibração é reaproveitada sem nenhum toque. Só números: nenhuma imagem.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from desktop import config

FORMAT = 1


@dataclass(frozen=True)
class SavedCalibration:
    matrix: np.ndarray
    markers: dict[int, list[tuple[float, float]]]  # id → 4 cantos em camera_norm
    screen: tuple[int, int]
    saved_at: str

    def marker_shift(self, observation) -> tuple[float, int]:
        """(maior diferença por canto, marcadores em comum) entre a gravada e a observação."""
        worst, common = 0.0, 0
        for marker_id, corners in observation.items():
            old = self.markers.get(int(marker_id))
            if old is None:
                continue
            common += 1
            for (ox, oy), p in zip(old, corners):
                worst = max(worst, abs(ox - p.x), abs(oy - p.y))
        return worst, common

    def matches(self, observation, screen: tuple[int, int]) -> bool:
        worst, common = self.marker_shift(observation)
        return (tuple(screen) == tuple(self.screen) and common >= config.MARKER_REFERENCE_MIN_VISIBLE
                and worst <= config.CALIB_REUSE_TOLERANCE)


def save(path: Path, matrix: np.ndarray, observation, screen: tuple[int, int]) -> None:
    data = {"format": FORMAT, "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "screen": [int(screen[0]), int(screen[1])],
            "matrix": [[float(v) for v in row] for row in np.asarray(matrix)],
            "markers": {str(int(i)): [[round(p.x, 5), round(p.y, 5)] for p in corners]
                        for i, corners in observation.items()}}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def load(path: Path | None) -> SavedCalibration | None:
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("format") != FORMAT:
            return None
        matrix = np.array(data["matrix"], dtype=np.float64)
        if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
            return None
        markers = {int(k): [(float(x), float(y)) for x, y in v] for k, v in data["markers"].items()}
        return SavedCalibration(matrix, markers, tuple(data["screen"]), data.get("saved_at", ""))
    except (OSError, ValueError, KeyError, TypeError):
        return None
