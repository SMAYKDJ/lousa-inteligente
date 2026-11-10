"""Reconhecimento de poses da mão com nota e histerese (D022).

Adaptado de open-source-hands (Meticulai), licença MIT, © 2026 abouchedidxcode:
https://github.com/abouchedidxcode/open-source-hands (commit dd79fb7), arquivos
src/kit/features.ts, poses.ts e engine.ts. Ver docs/references.md.

O que muda em relação ao reconhecimento anterior (hand_tracker.classify_pose):
- **Filtro One Euro nos 21 pontos** (imagem e mundo) antes de medir a mão, e
  não só no cursor. A pose deixa de oscilar com o tremor dos pontos.
- **Forma da mão pelos pontos 3D do mundo** (metros, imunes à rotação), quando
  o MediaPipe os entrega. Antes: pontos 2D da imagem, que se deformam quando a
  mão gira em relação à câmera.
- **Dobra do dedo pela soma dos ângulos das articulações** (a da base conta
  metade). Antes: razão de distâncias pulso→ponta ÷ pulso→articulação.
- **Pose = nota de 0 a 1** (√(média geométrica × pior regra)), com limiar de
  entrada e de saída, margem para trocar de pose e confirmação em
  milissegundos. Antes: classe por limiar fixo + contagem de quadros.

Adaptações para a lousa (diferentes do kit):
- "Mão aberta" não exige a palma voltada para a câmera: na lousa a câmera
  costuma ver as costas da mão do professor.
- Só as poses que a lousa usa, mais algumas parecidas que "absorvem" mãos
  ambíguas (V, garra, OK) para elas não virarem "apontar".
- "Apontar" aceita os outros dedos meio dobrados (ver POSES).
- O tempo vem do relógio do quadro (ms do MediaPipe), não de performance.now().

Puro Python (sem numpy, sem Qt): testável com as mãos sintéticas de synthetic_hands.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Sequence

from desktop import config
from desktop.core.one_euro import OneEuro

Vec = tuple[float, float, float]

# Cadeias de articulações por dedo (polegar … mínimo), cada uma começando no pulso.
CHAINS = ((0, 1, 2, 3, 4), (0, 5, 6, 7, 8), (0, 9, 10, 11, 12), (0, 13, 14, 15, 16), (0, 17, 18, 19, 20))

# Dobra (radianos) considerada reta / totalmente dobrada. Valores do kit (medidos nos pontos do mundo).
FINGER_BEND = (0.45, 3.1)
THUMB_BEND = (0.35, 1.5)


def clamp01(v: float) -> float:
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def smoothstep(e0: float, e1: float, x: float) -> float:
    t = clamp01((x - e0) / (e1 - e0))
    return t * t * (3 - 2 * t)


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _len(a: Vec) -> float:
    return math.sqrt(_dot(a, a))


def _dist(a: Vec, b: Vec) -> float:
    return _len(_sub(a, b))


def _bend(a: Vec, b: Vec, c: Vec) -> float:
    """Dobra na articulação b: 0 com a-b-c em linha reta, π dobrado para trás."""
    u, v = _sub(b, a), _sub(c, b)
    lu, lv = _len(u), _len(v)
    if lu < 1e-9 or lv < 1e-9:
        return 0.0
    return math.acos(max(-1.0, min(1.0, _dot(u, v) / (lu * lv))))


def _unit2(x: float, y: float) -> tuple[float, float]:
    n = math.hypot(x, y) or 1.0
    return x / n, y / n


def _angle2(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.acos(max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1])))


@dataclass(frozen=True)
class HandFeatures:
    curl: tuple[float, float, float, float, float]  # 0 reto … 1 dobrado (polegar … mínimo)
    thumb_out: float  # polegar afastado da palma (0 recolhido … 1 para fora)
    tip_gap: tuple[float, float, float, float]  # ponta do polegar ↔ pontas ÷ palma (indicador … mínimo)
    spread: tuple[float, float, float]  # ângulo entre dedos vizinhos (rad), no plano da imagem
    point_dir: tuple[float, float]  # direção do indicador na imagem
    thumb_dir: tuple[float, float]  # direção do polegar na imagem
    openness: float  # 1 − dobra média dos 4 dedos


def shape_points(image: Sequence[Vec], world: Sequence[Vec] | None, aspect: float) -> list[Vec]:
    """Pontos 3D para medir a forma: os do mundo se houver, senão os da imagem tornados isotrópicos."""
    if world is not None and len(world) == 21:
        return list(world)
    return [(p[0] * aspect, p[1], p[2] * aspect * 0.6) for p in image]


def compute_features(image: Sequence[Vec], world: Sequence[Vec] | None, aspect: float) -> HandFeatures:
    P = shape_points(image, world, aspect)
    S = image
    palm_len = max(_dist(P[0], P[9]), 1e-6)
    curl = [0.0] * 5
    for f, c in enumerate(CHAINS):
        if f == 0:
            b = _bend(P[c[1]], P[c[2]], P[c[3]]) + _bend(P[c[2]], P[c[3]], P[c[4]])
            curl[0] = clamp01((b - THUMB_BEND[0]) / (THUMB_BEND[1] - THUMB_BEND[0]))
        else:
            # a dobra da base conta metade: mão espalmada dobrada na base continua "aberta"
            b = (0.5 * _bend(P[c[0]], P[c[1]], P[c[2]]) + _bend(P[c[1]], P[c[2]], P[c[3]])
                 + _bend(P[c[2]], P[c[3]], P[c[4]]))
            curl[f] = clamp01((b - FINGER_BEND[0]) / (FINGER_BEND[1] - FINGER_BEND[0]))
    t_out = min(_dist(P[4], P[5]), _dist(P[4], P[9]) * 1.15) / palm_len
    thumb_out = smoothstep(0.32, 0.62, t_out) * (1 - 0.5 * smoothstep(0.6, 1, curl[0]))
    tip_gap = tuple(_dist(P[4], P[t]) / palm_len for t in (8, 12, 16, 20))

    def direction(m: int, t: int) -> tuple[float, float]:
        return _unit2((S[t][0] - S[m][0]) * aspect, S[t][1] - S[m][1])
    d_i, d_m, d_r, d_p = direction(5, 8), direction(9, 12), direction(13, 16), direction(17, 20)
    spread = (_angle2(d_i, d_m), _angle2(d_m, d_r), _angle2(d_r, d_p))
    thumb_dir = _unit2((S[4][0] - S[2][0]) * aspect, S[4][1] - S[2][1])
    openness = 1 - sum(curl[1:]) / 4
    return HandFeatures(tuple(curl), thumb_out, tip_gap, spread, d_i, thumb_dir, openness)


# --- poses ------------------------------------------------------------------------

def _deg(d: float) -> float:
    return d * math.pi / 180


def pinch_strength(f: HandFeatures, i: int = 0) -> float:
    """0..1: ponta do polegar na ponta do dedo i (0 = indicador)."""
    return 1 - smoothstep(0.2, 0.42, f.tip_gap[i])


def _l_shape(f: HandFeatures) -> float:
    c = max(-1.0, min(1.0, f.thumb_dir[0] * f.point_dir[0] + f.thumb_dir[1] * f.point_dir[1]))
    return smoothstep(_deg(22), _deg(42), math.acos(c))


@dataclass(frozen=True)
class PoseDef:
    id: str
    fingers: tuple[str, str, str, str, str]  # regra por dedo: ext, curl, half, notcurl, notext, any
    extra: Callable[[HandFeatures], float] | None = None


#: Poses usadas pela lousa ("point", "open", "fist", "pinch") e algumas parecidas que
#: absorvem mãos ambíguas. "open" sem exigir a palma para a câmera (ver docstring).
POSES: tuple[PoseDef, ...] = (
    PoseDef("open", ("ext", "ext", "ext", "ext", "ext")),
    PoseDef("fist", ("any", "curl", "curl", "curl", "curl"),
            lambda f: 1 - 0.6 * smoothstep(0.55, 0.9, f.thumb_out)),
    PoseDef("claw", ("any", "half", "half", "half", "half"),
            lambda f: smoothstep(0.28, 0.45, f.tip_gap[0])),
    # Kit: médio/anelar/mínimo "curl" (bem dobrados, > 0,74). O apontar real do professor
    # (gravações de 2026-11-07) tem esses dedos meio dobrados (~0,55): o kit reconhecia só
    # 63–66% do tempo em que ele apontava. Com "notext" (não esticados): 85–92%.
    PoseDef("point", ("any", "ext", "notext", "notext", "notext"),
            lambda f: 1 - 0.45 * f.thumb_out * _l_shape(f)),
    PoseDef("victory", ("any", "ext", "ext", "curl", "curl"),
            lambda f: smoothstep(_deg(9), _deg(17), f.spread[0])),
    PoseDef("pinch", ("any", "notcurl", "any", "any", "any"), pinch_strength),
    PoseDef("ok", ("any", "any", "ext", "ext", "ext"), pinch_strength),
)


def rule_score(rule: str, curl: float, thumb_out: float, thumb: bool) -> float:
    if rule == "any":
        return 1.0
    # no polegar, "esticado" é estar para fora da palma, não a própria dobra
    ext = thumb_out if thumb else 1 - smoothstep(0.3, 0.62, curl)
    cur = 1 - thumb_out if thumb else smoothstep(0.5, 0.74, curl)
    if rule == "ext":
        return ext
    if rule == "curl":
        return cur
    if rule == "notcurl":
        return 1 - cur
    if rule == "notext":
        return 1 - ext
    if rule == "half":
        return 1.0 if thumb else smoothstep(0.15, 0.32, curl) * (1 - smoothstep(0.62, 0.8, curl))
    raise ValueError(rule)


def score_pose(pose: PoseDef, f: HandFeatures) -> float:
    """0..1: √(média geométrica × pior regra) — um dedo claramente errado derruba a pose,
    oscilações pequenas em todos só arranham. Poses mais restritas ganham empates."""
    log_sum, n, worst = 0.0, 0, 1.0

    def add(v: float) -> None:
        nonlocal log_sum, n, worst
        c = max(1e-4, v)
        log_sum += math.log(c)
        n += 1
        worst = min(worst, c)
    for i, rule in enumerate(pose.fingers):
        if rule != "any":
            add(rule_score(rule, f.curl[i], f.thumb_out, i == 0))
    if pose.extra is not None:
        add(pose.extra(f))
    g = math.sqrt(math.exp(log_sum / n) * worst) if n else 0.0
    return min(1.0, g * (0.93 + 0.01 * n))


# --- motor por mão: filtro + nota + histerese --------------------------------------

#: Nome da pose do kit → nome usado na lousa (pen_state, D018).
LEGACY_NAME = {"point": "pointing", "open": "open", "fist": "fist"}


@dataclass
class _Track:
    handedness: str
    center: tuple[float, float]
    last_seen: float
    filters: list[OneEuro]
    wfilters: list[OneEuro]
    pose: str | None = None
    cand: str | None = None
    cand_since: float = 0.0


@dataclass(frozen=True)
class GestureResult:
    pose: str | None  # pose estável do kit ("point", "open", …) ou None
    scores: dict[str, float] = field(default_factory=dict)
    features: HandFeatures | None = None
    pinch: float = 0.0  # força da pinça 0..1
    pinch_gap: float = 9.9  # polegar↔indicador ÷ palma (para D021)
    image: tuple[Vec, ...] = ()  # pontos da imagem já filtrados

    @property
    def board_pose(self) -> str:
        """Nome usado pela caneta: pointing / open / fist / other."""
        return LEGACY_NAME.get(self.pose or "", "other")


def _center(points: Sequence[Vec]) -> tuple[float, float]:
    return (points[0][0] + points[9][0]) / 2, (points[0][1] + points[9][1]) / 2


class GestureEngine:
    """Uma instância por fluxo de quadros (thread da visão). `update` a cada quadro."""

    def __init__(self) -> None:
        self.tracks: list[_Track] = []

    def _new_track(self, handedness: str, center: tuple[float, float], t: float) -> _Track:
        def mk() -> list[OneEuro]:
            return [OneEuro(config.GESTURE_FILTER_MIN_CUTOFF_HZ, config.GESTURE_FILTER_BETA,
                            config.GESTURE_FILTER_D_CUTOFF_HZ) for _ in range(63)]
        return _Track(handedness, center, t, mk(), mk())

    def _assign(self, hands: Sequence[tuple[Sequence[Vec], Sequence[Vec] | None, str]],
                t: float) -> list[_Track]:
        """Mesma mão do quadro anterior = a mais próxima (até 0,35, +0,1 se a lateralidade mudou)."""
        free = list(self.tracks)
        out = []
        for image, _, handedness in hands:
            c = _center(image)
            best, best_d = None, 0.35
            for tr in free:
                d = math.hypot(tr.center[0] - c[0], tr.center[1] - c[1]) + (0 if tr.handedness == handedness else 0.1)
                if d < best_d:
                    best, best_d = tr, d
            if best is None:
                best = self._new_track(handedness, c, t)
                self.tracks.append(best)
            else:
                free.remove(best)
            best.center, best.handedness, best.last_seen = c, handedness, t
            out.append(best)
        return out

    def update(self, hands: Sequence[tuple[Sequence[Vec], Sequence[Vec] | None, str]],
               t_s: float, aspect: float) -> list[GestureResult]:
        """`hands`: (pontos da imagem, pontos do mundo ou None, lateralidade) por mão."""
        tracks = self._assign(hands, t_s)
        self.tracks = [tr for tr in self.tracks if t_s - tr.last_seen <= config.GESTURE_LOST_S]
        return [self._update_hand(tr, image, world, t_s, aspect)
                for tr, (image, world, _) in zip(tracks, hands)]

    def _update_hand(self, tr: _Track, image, world, t: float, aspect: float) -> GestureResult:
        def filt(points, filters, scale):
            return tuple((filters[i * 3](p[0] * scale, t) / scale,
                          filters[i * 3 + 1](p[1] * scale, t) / scale,
                          filters[i * 3 + 2](p[2] * scale, t) / scale) for i, p in enumerate(points))
        img = filt(image, tr.filters, 1.0)
        # pontos do mundo em metros (~0,1 por mão): ×10 para a velocidade do filtro ter escala parecida
        wld = filt(world, tr.wfilters, 10.0) if world is not None and len(world) == 21 else None
        f = compute_features(img, wld, aspect)
        scores = {p.id: score_pose(p, f) for p in POSES}
        best = max(scores, key=scores.get)
        best_s = scores[best]
        cur = tr.pose
        cur_s = scores.get(cur, 0.0) if cur else 0.0
        want = cur
        if cur and cur_s < config.GESTURE_EXIT:
            want = None
        if best_s >= config.GESTURE_ENTER and best != cur and (not cur or best_s > cur_s + config.GESTURE_MARGIN):
            want = best
        if want != cur:
            if tr.cand != want:
                tr.cand, tr.cand_since = want, t
            # cair para "nenhuma pose" espera mais, para a pose não piscar entre quadros;
            # "aberta"/"fechada" têm sua própria confirmação, maior (D039)
            if want is None:
                need = config.GESTURE_DEBOUNCE_S * 1.6
            else:
                need = config.GESTURE_DEBOUNCE_BY_POSE_S.get(want, config.GESTURE_DEBOUNCE_S)
            if t - tr.cand_since >= need:
                tr.pose = want
        else:
            tr.cand = cur
        return GestureResult(tr.pose, scores, f, pinch_strength(f), f.tip_gap[0], img)
