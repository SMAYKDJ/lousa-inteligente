"""Comportamento de cada ferramenta com a caneta (pose) e a posição do dedo (Fase 4).

Recebe, a cada atualização: ferramenta, caneta na lousa (pen_state.py), ponto
do dedo em surface_norm (ou None) e se o dedo está sobre a interface (sidebar,
confirmação). Altera o Board e mantém a prévia (forma em construção, traço em
andamento, rastro do ponteiro). Sem Qt.
"""

from __future__ import annotations

import math

from desktop import config
from desktop.drawing.board import (Board, Ellipse, Point, Rectangle, Stroke, bounds, resample,
                                  scale_item, translate)
from desktop.drawing.style import DrawingStyle
from desktop.interface.sidebar_model import Tool


class ToolController:
    def __init__(self, board: Board, style: DrawingStyle | None = None) -> None:
        self.board = board
        self.style = style or DrawingStyle()
        self.preview = None  # Stroke/Ellipse/Rectangle em construção
        self.trail: list[tuple[Point, float]] = []  # rastro do ponteiro
        self._stroke: list[Point] = []
        self._smoothed: Point | None = None
        self._shape_start: Point | None = None
        self._erasing = False
        self._tool: Tool | None = None
        self._up_since: float | None = None  # caneta levantada durante uma forma
        self.selected: int | None = None  # item seguro pelo Selecionar
        self._grab_point: Point | None = None
        self._grab: dict | None = None  # D035: desenho seguro (base, início, palma de referência)
        self._moved = 0.0
        self.resizing: dict | None = None  # Selecionar → redimensionar (etapa 4.6)
        self._two_hand: dict | None = None  # zoom com duas mãos durante o redimensionar (D024)

    def update(self, tool: Tool, pen_down: bool, point: Point | None, over_ui: bool,
               size: tuple[float, float], now: float, openness: float | None = None) -> list[dict]:
        events: list[dict] = []
        if tool != self._tool:
            events += self._finish(size)
            self._tool = tool
        active = pen_down and point is not None and not over_ui

        if tool is Tool.POINTER:
            if point is not None and not over_ui:
                self.trail.append((point, now))
            self.trail = [(p, t) for p, t in self.trail if now - t <= config.POINTER_TRAIL_S]
            return events
        self.trail = []

        if tool is Tool.SELECT:
            return events + self._select_tool(active, point, over_ui, size, now, openness)

        if not active:
            if tool in (Tool.CIRCLE, Tool.RECTANGLE) and self._shape_start is not None:
                # Forma em construção: só conclui se a caneta ficar levantada de fato.
                if self._up_since is None:
                    self._up_since = now
                if now - self._up_since < config.SHAPE_RELEASE_S:
                    return events
            return events + self._finish(size)
        self._up_since = None

        if tool is Tool.BRUSH:
            self._brush(point, size)
        elif tool is Tool.ERASER:
            if not self._erasing:
                self.board.begin_group()
                self._erasing = True
            radius = self.style.eraser_frac * size[1]
            if self.board.erase(point, radius, size):
                events.append({"event": "draw_erase"})
        elif tool in (Tool.CIRCLE, Tool.RECTANGLE):
            if self._shape_start is None:
                self._shape_start = point
            kind = Ellipse if tool is Tool.CIRCLE else Rectangle
            self.preview = kind(self._shape_start, point, self.style.color, self.style.width_frac)
        return events

    # --- Selecionar: arrastar e redimensionar ------------------------------------

    def _select_tool(self, active: bool, point: Point | None, over_ui: bool,
                     size: tuple[float, float], now: float, openness: float | None) -> list[dict]:
        """Indicador esticado sobre um desenho: pega e arrasta (movimento para os lados).
        Ao soltar, o desenho continua selecionado e o sinal de tamanho o redimensiona:
        com `RESIZE_SIGNAL = "size"` (D035), o tamanho da mão visto pela câmera — aproximar
        a mão da câmera amplia, aproximar da lousa reduz; com "openness", abrir/fechar a mão.
        Com o sinal parado por 1 s, o tamanho fica. `openness` recebe o sinal escolhido."""
        events: list[dict] = []
        by_size = config.RESIZE_SIGNAL == "size"
        if active:
            if self.resizing is not None:
                events += self._end_resize()  # apontar de novo confirma o tamanho
            if by_size:
                self._select_scaling(point, size, now, openness)
            else:
                self._select(point, size)
            return events
        if self.resizing is not None:
            return self._resize_step(openness, now)
        if by_size and self.selected is not None and self._grab_point is not None:
            # Soltou (D035): posição e tamanho ficam; 1 s de confirmação (anel) e acabou.
            index, grab = self.selected, self._grab
            item = self.board.items[index]
            x0, y0, x1, y1 = bounds(item, size)
            self.resizing = {"index": index, "confirm_only": True, "start": now, "still_since": now,
                             "scale": grab["scale"] if grab else 1.0,
                             "baseline": grab["palm_ref"] if grab else None,
                             "smoothed": grab["palm"] if grab else None, "still_value": None,
                             "base": item, "anchor": ((x0 + x1) / 2, (y0 + y1) / 2)}
            self._grab_point, self._grab = None, None
            if openness is None:  # sem mão (ou mouse): confirma na hora
                return events + self._end_resize()
            return events
        if self.selected is not None and self._grab_point is not None:
            index = self.selected
            events += self._end_drag()
            if openness is not None and point is not None and not over_ui:
                self._start_resize(index, now, size)
            else:
                self.selected = None
        else:
            self.selected, self._grab_point, self._moved = None, None, 0.0
        return events

    def _end_drag(self) -> list[dict]:
        self.board.end_group()
        events = [{"event": "draw_move", "px": round(self._moved)}] if self._moved > 0 else []
        self._grab_point, self._moved = None, 0.0
        return events

    def _start_resize(self, index: int, now: float, size: tuple[float, float]) -> None:
        item = self.board.items[index]
        x0, y0, x1, y1 = bounds(item, size)
        self.board.begin_group()
        self.selected = index
        self.resizing = {"index": index, "base": item, "anchor": ((x0 + x1) / 2, (y0 + y1) / 2),
                         "start": now, "baseline": None, "smoothed": None, "scale": 1.0,
                         "still_value": None, "still_since": now}

    def two_hand(self, zoom: float | None, now: float, size: tuple[float, float]) -> list[dict]:
        """Zoom com duas mãos (D024): com um desenho em redimensionamento, afastar/aproximar
        as mãos amplia/reduz. Enquanto as duas mãos pegam, a abertura da mão é ignorada;
        ao soltar, a abertura volta a valer a partir do tamanho atual."""
        r = self.resizing
        if r is None:
            self._two_hand = None
            return []
        if zoom is None:
            if self._two_hand is None:
                return []
            final = self._two_hand["scale"]
            self._two_hand = None
            self._rebase(now)
            return [{"event": "draw_zoom", "scale": round(final, 2)}]
        if self._two_hand is None:
            self._rebase(now)
            self._two_hand = {"scale": 1.0}
        scale = min(config.RESIZE_MAX_SCALE, max(config.RESIZE_MIN_SCALE, zoom))
        self.board.replace(r["index"], scale_item(r["base"], scale, r["anchor"]))
        self._two_hand["scale"] = scale
        r["scale"] = scale
        return []

    def _rebase(self, now: float) -> None:
        """O tamanho atual vira a nova base; a abertura de referência é medida de novo."""
        r = self.resizing
        r["base"] = self.board.items[r["index"]]
        r["scale"], r["baseline"], r["smoothed"], r["start"] = 1.0, None, None, now
        r["still_value"], r["still_since"] = None, now

    def _select_scaling(self, point: Point, size: tuple[float, float], now: float,
                        palm: float | None) -> None:
        """D035: segurando o desenho com o indicador, ir para os lados move e aproximar a
        mão da câmera (palma maior) amplia / da lousa (palma menor) reduz, ao mesmo tempo."""
        if self._grab_point is None:
            radius = config.SELECT_RADIUS_FRAC * size[1]
            self.selected = self.board.hit(point, radius, size)
            self._grab_point = point
            self._grab = None
            if self.selected is not None:
                self.board.begin_group()
                base = self.board.items[self.selected]
                self._grab = {"base": base, "start": point, "since": now, "palm_ref": None,
                              "palm": None, "scale": 1.0}
            return
        g = self._grab
        if self.selected is None or g is None:
            return
        if palm is not None and now - g["since"] >= config.SELECT_PALM_SETTLE_S:
            if g["palm_ref"] is None:
                g["palm_ref"] = g["palm"] = palm
            else:
                g["palm"] += config.RESIZE_SMOOTHING * (palm - g["palm"])
                ratio = g["palm"] / max(g["palm_ref"], 1e-6)
                dz = config.RESIZE_SIZE_DEADZONE
                # Zona morta: o ruído da palma não muda o tamanho de quem só está movendo.
                ratio = ratio / (1 + dz) if ratio > 1 + dz else ratio / (1 - dz) if ratio < 1 - dz else 1.0
                scale = ratio ** config.RESIZE_SIZE_GAIN
                g["scale"] = min(config.RESIZE_MAX_SCALE, max(config.RESIZE_MIN_SCALE, scale))
        dx, dy = point[0] - g["start"][0], point[1] - g["start"][1]
        moved = translate(g["base"], dx, dy)
        x0, y0, x1, y1 = bounds(moved, size)
        anchor = ((x0 + x1) / 2, (y0 + y1) / 2)
        item = scale_item(moved, g["scale"], anchor) if abs(g["scale"] - 1) > 0.003 else moved
        if item != self.board.items[self.selected]:
            self.board.replace(self.selected, item)
        self._moved += math.hypot((point[0] - self._grab_point[0]) * size[0],
                                  (point[1] - self._grab_point[1]) * size[1])
        self._grab_point = point

    def _resize_step(self, openness: float | None, now: float) -> list[dict]:
        r = self.resizing
        if r.get("confirm_only"):
            # Desenho solto: espera 1 s (ou a mão sumir) e confirma posição e tamanho.
            if openness is None or now - r["still_since"] >= config.RESIZE_HOLD_S:
                return self._end_resize()
            return []
        if self._two_hand is not None:
            return []  # as duas mãos comandam o tamanho agora
        if openness is None:  # mão perdida: fica o tamanho atual
            return self._end_resize()
        if now - r["start"] < config.RESIZE_SETTLE_S:
            return []  # a mão ainda está saindo da pose de apontar
        if r["baseline"] is None:
            r["baseline"] = r["smoothed"] = r["still_value"] = openness
            r["still_since"] = now
            return []
        r["smoothed"] += config.RESIZE_SMOOTHING * (openness - r["smoothed"])
        by_size = config.RESIZE_SIGNAL == "size"
        gain = config.RESIZE_SIZE_GAIN if by_size else config.RESIZE_GAIN
        scale = (r["smoothed"] / max(r["baseline"], 1e-6)) ** gain
        scale = min(config.RESIZE_MAX_SCALE, max(config.RESIZE_MIN_SCALE, scale))
        if abs(scale - r["scale"]) > 0.003:
            self.board.replace(r["index"], scale_item(r["base"], scale, r["anchor"]))
            r["scale"] = scale
        if by_size:
            moving = abs(r["smoothed"] / max(r["still_value"], 1e-6) - 1) > config.RESIZE_SIZE_STILL_TOLERANCE
        else:
            moving = abs(r["smoothed"] - r["still_value"]) > config.RESIZE_STILL_TOLERANCE
        if moving:
            r["still_value"], r["still_since"] = r["smoothed"], now
        elif now - r["still_since"] >= config.RESIZE_HOLD_S:
            return self._end_resize()
        return []

    def resize_progress(self, now: float) -> float:
        """0–1: quanto falta da mão parada para confirmar o tamanho (para o desenho do anel)."""
        r = self.resizing
        if r is None or (r["baseline"] is None and not r.get("confirm_only")):
            return 0.0
        return min(1.0, (now - r["still_since"]) / config.RESIZE_HOLD_S)

    def _end_resize(self) -> list[dict]:
        r, self.resizing, self.selected = self.resizing, None, None
        self._two_hand = None
        self.board.end_group()
        if r is None:
            return []
        if r.get("confirm_only"):
            events = [{"event": "draw_move", "px": round(self._moved)}] if self._moved > 0 else []
            self._moved = 0.0
            if abs(r["scale"] - 1.0) > 0.01:
                events.append({"event": "draw_resize", "scale": round(r["scale"], 2), "signal": "size",
                               "palm_ref": None if r["baseline"] is None else round(r["baseline"], 1),
                               "palm_end": None if r["smoothed"] is None else round(r["smoothed"], 1)})
            return events
        if abs(r["scale"] - 1.0) > 0.01:
            # Abertura de referência e final: para ajustar o ganho com dados reais.
            return [{"event": "draw_resize", "scale": round(r["scale"], 2), "signal": config.RESIZE_SIGNAL,
                     "openness_ref": None if r["baseline"] is None else round(r["baseline"], 2),
                     "openness_end": None if r["smoothed"] is None else round(r["smoothed"], 2)}]
        return [{"event": "draw_resize_none",
                 "openness_ref": None if r["baseline"] is None else round(r["baseline"], 2)}]

    def _select(self, point: Point, size: tuple[float, float]) -> None:
        if self._grab_point is None:
            radius = config.SELECT_RADIUS_FRAC * size[1]
            self.selected = self.board.hit(point, radius, size)
            self._grab_point = point  # mesmo sem item: só pega o que estiver sob o dedo ao descer
            if self.selected is not None:
                self.board.begin_group()
            return
        if self.selected is None:
            return
        dx, dy = point[0] - self._grab_point[0], point[1] - self._grab_point[1]
        self.board.move(self.selected, dx, dy)
        self._moved += math.hypot(dx * size[0], dy * size[1])
        self._grab_point = point

    def _brush(self, point: Point, size: tuple[float, float]) -> None:
        a = config.STROKE_SMOOTHING
        s = self._smoothed
        s = point if s is None else (s[0] + a * (point[0] - s[0]), s[1] + a * (point[1] - s[1]))
        self._smoothed = s
        if not self._stroke or math.hypot((s[0] - self._stroke[-1][0]) * size[0],
                                          (s[1] - self._stroke[-1][1]) * size[1]) >= 1.5:
            self._stroke.append(s)
        self.preview = Stroke(tuple(self._stroke), self.style.color, self.style.width_frac)

    def _finish(self, size: tuple[float, float]) -> list[dict]:
        """Caneta levantada (ou troca de ferramenta): confirma o que estava em construção."""
        events: list[dict] = []
        aspect = size[0] / max(size[1], 1)
        if self._stroke:
            points = resample(self._stroke, config.STROKE_SPACING_FRAC, aspect)
            if len(points) == 1:
                points = points * 2  # um toque vira um ponto
            self.board.add(Stroke(tuple(points), self.preview.color, self.preview.width))
            events.append({"event": "draw_stroke", "points": len(points)})
            if config.SHAPE_SNAP_ENABLED:
                # Traço que parece forma vira a forma perfeita (D033). É uma troca no
                # histórico: Voltar devolve o traço como foi desenhado.
                from desktop.drawing.shape_snap import recognize
                snap = recognize(points, size, self.preview.color, self.preview.width)
                if snap is not None:
                    self.board.replace(len(self.board.items) - 1, snap.item)
                    events.append({"event": "draw_snap", "shape": snap.kind, "error": round(snap.error, 3)})
        if isinstance(self.preview, (Ellipse, Rectangle)) and self._shape_start is not None:
            if isinstance(self.preview, Ellipse):
                a, b = self.preview.center, self.preview.edge
            else:
                a, b = self.preview.a, self.preview.b
            if math.hypot((a[0] - b[0]) * aspect, a[1] - b[1]) >= config.SHAPE_MIN_FRAC:
                self.board.add(self.preview)
                events.append({"event": "draw_shape",
                               "shape": "circle" if isinstance(self.preview, Ellipse) else "rectangle"})
        if self._erasing:
            self.board.end_group()
            self._erasing = False
        if self.resizing is not None:
            events += self._end_resize()
        elif self.selected is not None and self._grab_point is not None:
            events += self._end_drag()
        self.selected, self._grab_point, self._moved = None, None, 0.0
        self._stroke, self._smoothed, self._shape_start, self.preview = [], None, None, None
        self._up_since = None
        return events
