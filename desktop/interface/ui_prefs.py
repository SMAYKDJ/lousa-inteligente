"""Preferências da lousa que valem de uma aula para a outra (D031, RF30).

Guarda onde o professor deixou a sidebar (borda, posição, orientação) e o
estilo do pincel e da borracha (cor, espessura, tamanho). Arquivo JSON
pequeno na pasta do projeto, gravado só quando algo muda, com troca atômica
(um desligamento no meio não corrompe). Um arquivo inválido é ignorado: a
lousa abre com o padrão.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from desktop import config

FORMAT = 1


def snapshot(sidebar, style) -> dict[str, Any]:
    out: dict[str, Any] = {"format": FORMAT,
                           "style": {"color": style.color_index, "width": style.width_index,
                                     "eraser": style.eraser_index}}
    if sidebar is not None:
        out["sidebar"] = {"edge": sidebar.edge.value, "offset": round(float(sidebar.offset), 4),
                          "orientation": sidebar.orientation.value}
    return out


def load(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("format") == FORMAT else None


def save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def apply_style(data: dict[str, Any] | None, style) -> None:
    st = (data or {}).get("style") or {}

    def pick(key, n, current):
        v = st.get(key)
        return v if isinstance(v, int) and 0 <= v < n else current

    style.color_index = pick("color", len(config.BRUSH_COLORS), style.color_index)
    style.width_index = pick("width", len(config.BRUSH_WIDTHS_FRAC), style.width_index)
    style.eraser_index = pick("eraser", len(config.ERASER_RADII_FRAC), style.eraser_index)


def apply_sidebar(data: dict[str, Any] | None, sidebar) -> None:
    from desktop.interface.sidebar_model import Edge, Orientation
    sb = (data or {}).get("sidebar") or {}
    try:
        sidebar.edge = Edge(sb.get("edge", sidebar.edge.value))
        sidebar.orientation = Orientation(sb.get("orientation", sidebar.orientation.value))
    except ValueError:
        return
    offset = sb.get("offset")
    if isinstance(offset, (int, float)):
        sidebar.offset = min(0.95, max(0.05, float(offset)))
