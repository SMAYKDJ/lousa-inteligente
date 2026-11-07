"""Guardar e recuperar as anotações (etapa 6.3, D027).

As anotações de cada slide (SlideBook) vão para um arquivo JSON por aula, em
anotacoes/aula-AAAAMMDD-HHMMSS.json, salvo a cada mudança (com um pequeno
intervalo) e ao fechar. Tudo em surface_norm: o arquivo vale para qualquer tela.

Não guarda imagens da câmera nem do slide (CLAUDE.md §11): só os traços e formas.
O histórico de Voltar/Avançar não é guardado.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from desktop.drawing.board import Board, Ellipse, Rectangle, Stroke
from desktop.presentation.slides import SlideBook

FORMAT = 1


def item_to_dict(item) -> dict:
    if isinstance(item, Stroke):
        return {"type": "stroke", "points": [[round(x, 5), round(y, 5)] for x, y in item.points],
                "color": item.color, "width": item.width}
    if isinstance(item, Ellipse):
        return {"type": "ellipse", "center": list(item.center), "edge": list(item.edge),
                "color": item.color, "width": item.width}
    return {"type": "rectangle", "a": list(item.a), "b": list(item.b), "color": item.color, "width": item.width}


def item_from_dict(d: dict):
    kind = d["type"]
    if kind == "stroke":
        return Stroke(tuple(tuple(p) for p in d["points"]), d["color"], d["width"])
    if kind == "ellipse":
        return Ellipse(tuple(d["center"]), tuple(d["edge"]), d["color"], d["width"])
    if kind == "rectangle":
        return Rectangle(tuple(d["a"]), tuple(d["b"]), d["color"], d["width"])
    raise ValueError(f"tipo desconhecido: {kind}")


def book_to_dict(book: SlideBook) -> dict:
    return {"format": FORMAT, "saved": time.strftime("%Y-%m-%dT%H:%M:%S"), "current_slide": book.index + 1,
            "slides": {str(i + 1): [item_to_dict(it) for it in b.items]
                       for i, b in sorted(book._boards.items()) if b.items}}


def book_from_dict(data: dict) -> SlideBook:
    if data.get("format") != FORMAT:
        raise ValueError("formato de arquivo de anotações não reconhecido")
    book = SlideBook()
    for key, items in data.get("slides", {}).items():
        board = Board()
        board.items = tuple(item_from_dict(d) for d in items)  # sem histórico: começa limpo
        book._boards[int(key) - 1] = board
    book._boards.setdefault(0, Board())
    book.index = 0
    return book


def save(book: SlideBook, path: Path) -> None:
    """Grava num arquivo temporário e troca: um desligamento no meio não corrompe o arquivo."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(book_to_dict(book), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def load(path: Path) -> SlideBook:
    return book_from_dict(json.loads(path.read_text(encoding="utf-8")))


def latest(directory: Path, exclude: Path | None = None) -> Path | None:
    """Aula salva mais recente (com anotações), sem contar `exclude` (a aula atual)."""
    files = sorted(p for p in directory.glob("aula-*.json") if p != exclude)
    for p in reversed(files):
        try:
            if json.loads(p.read_text(encoding="utf-8")).get("slides"):
                return p
        except (OSError, ValueError):
            continue
    return None
