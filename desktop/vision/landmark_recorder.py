"""Gravação só dos pontos da mão, sem imagem (D024, opção --record).

Ideia do open-source-hands (MIT), que testa com o MediaPipe real sobre vídeos
gravados ("camera-check"). Aqui, por privacidade (CLAUDE.md §11), grava-se
**apenas** os 21 pontos de cada mão (imagem e mundo), a lateralidade e o tempo:
nenhuma imagem sai da memória. Com isso, uma sessão real pode ser reproduzida
depois (tools/replay_landmarks.py) para comparar reconhecimentos e ajustar
limiares com dados reais, sem câmera.

Formato: JSON Lines comprimido (gzip), uma linha por quadro processado:
  {"t": ms, "aspect": largura/altura, "hands": [{"h": "Right", "img": [[x,y,z]×21], "wld": [[x,y,z]×21] | null}]}
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Sequence

Vec = tuple[float, float, float]


class LandmarkRecorder:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._file = gzip.open(path, "wt", encoding="utf-8")
        self.frames = 0

    def write(self, t_ms: int, aspect: float,
              hands: Sequence[tuple[Sequence[Vec], Sequence[Vec] | None, str]]) -> None:
        def r(points):
            return None if points is None else [[round(c, 5) for c in p] for p in points]
        record = {"t": t_ms, "aspect": round(aspect, 4),
                  "hands": [{"h": label, "img": r(img), "wld": r(wld)} for img, wld, label in hands]}
        self._file.write(json.dumps(record, separators=(",", ":")) + "\n")
        self.frames += 1

    def close(self) -> None:
        self._file.close()


def read_recording(path: Path):
    """Quadros gravados: (t_s, aspect, [(img, wld, lateralidade)])."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            hands = [([tuple(p) for p in h["img"]], [tuple(p) for p in h["wld"]] if h["wld"] else None, h["h"])
                     for h in rec["hands"]]
            yield rec["t"] / 1000, rec["aspect"], hands
