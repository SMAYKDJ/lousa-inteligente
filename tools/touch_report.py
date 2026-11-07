"""Relatório do estudo do toque (etapa 5.3): encostado × no ar, só com os pontos da mão.

Cruza os eventos `touch_phase` do log da sessão (tecla T) com a gravação dos
pontos da mão (mesmo relógio monotônico) e mede, para cada sinal candidato,
quanto ele separa "encostado" de "no ar ~2 cm" (o caso difícil) e de "no ar ~5 cm".

Sinais (da mão que está na lousa: a de palma menor na imagem, a mais longe da câmera):
- `dobra_ponta`: dobra da última articulação do indicador (graus, pontos 3D). Encostar empurra a ponta.
- `dobra_meio`: dobra da articulação do meio do indicador (graus, 3D).
- `ponta_curta`: comprimento da falange da ponta ÷ falange de baixo, na imagem. A ponta
  encostada tende a ficar de frente para a câmera (encurta).
- `profundidade_ponta`: profundidade da ponta em relação ao punho (z da imagem do MediaPipe).
- `tremor`: quanto a ponta foge de uma reta ajustada em 5 quadros (‰ da largura). Encostada,
  a lousa segura o dedo.

Medidas:
- **separação (AUC)**: chance de um quadro "encostado" ter o sinal maior (ou menor) que um quadro
  "no ar". 0,5 = não separa; 1,0 = separa sempre. Quadros vizinhos são parecidos, então a AUC
  sozinha é otimista;
- **rodadas coerentes**: em quantas rodadas a média "encostado" ficou do mesmo lado da média
  "no ar" do mesmo lugar e movimento. Um sinal útil precisa das duas coisas.

Uso:
  python -m tools.touch_report                       # sessão mais recente com o estudo
  python -m tools.touch_report logs/session-….jsonl [logs/landmarks-….jsonl.gz]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from desktop import config
from desktop.vision.landmark_recorder import read_recording

FEATURES = ("dobra_ponta", "dobra_meio", "ponta_curta", "profundidade_ponta", "tremor")
USEFUL_AUC = 0.8


# --- leitura -----------------------------------------------------------------

def read_phases(session: Path) -> tuple[list[dict], str | None]:
    phases, recording = [], None
    with session.open(encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("event") == "touch_study_start":
                phases, recording = [], e.get("recording")  # vale o último estudo da sessão
            elif e.get("event") == "touch_phase":
                phases.append(e)
    return phases, recording


def latest_session(directory: Path = config.LOG_DIR) -> Path | None:
    for path in sorted(directory.glob("session-*.jsonl"), reverse=True):
        if "touch_phase" in path.read_text(encoding="utf-8", errors="ignore"):
            return path
    return None


# --- sinais --------------------------------------------------------------------

def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _angle(u, v) -> float | None:
    nu = math.sqrt(sum(x * x for x in u))
    nv = math.sqrt(sum(x * x for x in v))
    if nu < 1e-9 or nv < 1e-9:
        return None
    c = max(-1.0, min(1.0, sum(x * y for x, y in zip(u, v)) / (nu * nv)))
    return math.degrees(math.acos(c))


def _img(p, aspect):
    return (p[0] * aspect, p[1])  # x em unidades da altura: distâncias sem distorção


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def palm_size(img, aspect) -> float:
    return _dist(_img(img[0], aspect), _img(img[9], aspect))


def pick_board_hand(hands, aspect):
    """A mão na lousa é a mais longe da câmera: a de palma menor na imagem."""
    if not hands:
        return None
    return min(hands, key=lambda h: palm_size(h[0], aspect))


def frame_features(img, wld, aspect) -> dict[str, float]:
    out = {}
    pts = wld if wld else img
    a = _angle(_sub(pts[7], pts[6]), _sub(pts[8], pts[7]))
    b = _angle(_sub(pts[6], pts[5]), _sub(pts[7], pts[6]))
    if a is not None:
        out["dobra_ponta"] = a
    if b is not None:
        out["dobra_meio"] = b
    base = _dist(_img(img[5], aspect), _img(img[6], aspect))
    if base > 1e-6:
        out["ponta_curta"] = _dist(_img(img[7], aspect), _img(img[8], aspect)) / base
    palm = palm_size(img, aspect)
    if palm > 1e-6:
        out["profundidade_ponta"] = (img[8][2] - img[0][2]) / palm
    return out


def add_tremor(track: list[tuple[float, tuple[float, float], dict]], aspect: float) -> None:
    """Desvio da ponta em relação à reta ajustada nos 5 quadros em volta (‰ da largura)."""
    for i in range(2, len(track) - 2):
        window = track[i - 2:i + 3]
        ts = [w[0] for w in window]
        if ts[-1] - ts[0] > 0.4:  # buraco na gravação
            continue
        tm = sum(ts) / 5
        var = sum((t - tm) ** 2 for t in ts) or 1e-9
        dev = 0.0
        for k in (0, 1):
            vals = [w[1][k] for w in window]
            vm = sum(vals) / 5
            slope = sum((t - tm) * (v - vm) for t, v in zip(ts, vals)) / var
            fit = vm + slope * (track[i][0] - tm)
            dev += (track[i][1][k] - fit) ** 2
        track[i][2]["tremor"] = 1000 * math.sqrt(dev) / aspect  # ‰ da largura da imagem


# --- estatística -----------------------------------------------------------------

def auc(pos: list[float], neg: list[float]) -> float | None:
    """P(pos > neg) + ½ P(empate), por postos (Mann-Whitney)."""
    if not pos or not neg:
        return None
    allv = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    ranks, i = {}, 0
    rank_sum = 0.0
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        r = (i + 1 + j) / 2
        rank_sum += r * sum(1 for k in range(i, j) if allv[k][1] == 1)
        i = j
    n1, n0 = len(pos), len(neg)
    return (rank_sum - n1 * (n1 + 1) / 2) / (n1 * n0)


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def analyze(session: Path, recording: Path) -> dict:
    phases, _ = read_phases(session)
    if not phases:
        raise ValueError("a sessão não tem o estudo do toque (tecla T)")
    windows = [(p["start_ms"] / 1000 + config.TOUCH_STUDY_SETTLE_S, p["end_ms"] / 1000, i)
               for i, p in enumerate(phases)]
    per_phase: dict[int, list[dict]] = defaultdict(list)
    tracks: dict[int, list] = defaultdict(list)
    aspect_seen = 1.0
    for t, aspect, hands in read_recording(recording):
        hit = next((i for s, e, i in windows if s <= t <= e), None)
        if hit is None:
            continue
        hand = pick_board_hand(hands, aspect)
        if hand is None:
            continue
        img, wld, _ = hand
        aspect_seen = aspect
        feats = frame_features(img, wld, aspect)
        tracks[hit].append((t, _img(img[8], aspect), feats))
        per_phase[hit].append(feats)
    for track in tracks.values():
        add_tremor(track, aspect_seen)

    # Valores por rótulo e movimento.
    values: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    means: dict[tuple[int, str, str], dict[str, float]] = {}
    rounds = defaultdict(int)
    phase_info = []
    for i, p in enumerate(phases):
        key = (p["label"], p["motion"])
        rnd = rounds[key]
        rounds[key] += 1
        frames = per_phase.get(i, [])
        phase_info.append({"index": i, "label": p["label"], "motion": p["motion"], "round": rnd,
                           "frames": len(frames)})
        m = {}
        for f in FEATURES:
            vs = [fr[f] for fr in frames if f in fr]
            values[key][f].extend(vs)
            if vs:
                m[f] = _mean(vs)
        means[(rnd, p["label"], p["motion"])] = m

    comparisons = {}
    for air in ("air2", "air5"):
        for motion in ("still", "drag", "todos"):
            motions = ("still", "drag") if motion == "todos" else (motion,)
            res = {}
            for f in FEATURES:
                pos = [v for mo in motions for v in values[("touch", mo)][f]]
                neg = [v for mo in motions for v in values[(air, mo)][f]]
                a = auc(pos, neg)
                if a is None:
                    continue
                direction = "maior" if a >= 0.5 else "menor"
                sep = max(a, 1 - a)
                agree = total = 0
                for (rnd, label, mo), m in means.items():
                    if label != "touch" or mo not in motions:
                        continue
                    other = means.get((rnd, air, mo), {})
                    if f in m and f in other:
                        total += 1
                        agree += (m[f] > other[f]) == (direction == "maior")
                res[f] = {"auc": round(sep, 3), "touch_is": direction, "rounds_agree": agree,
                          "rounds": total, "touch_mean": _mean(pos), "air_mean": _mean(neg),
                          "n_touch": len(pos), "n_air": len(neg),
                          "useful": sep >= USEFUL_AUC and total > 0 and agree == total}
            if res:
                comparisons[f"{air}/{motion}"] = res
    return {"phases": phase_info, "comparisons": comparisons}


# --- saída ---------------------------------------------------------------------------

NAMES = {"air2": "no ar ~2 cm", "air5": "no ar ~5 cm", "still": "parado", "drag": "arrastando",
         "todos": "parado + arrastando"}


def format_report(result: dict) -> str:
    lines = []
    phases = result["phases"]
    few = [p for p in phases if p["frames"] < 20]
    lines.append(f"Etapas: {len(phases)} · quadros por etapa: "
                 f"{min(p['frames'] for p in phases)}–{max(p['frames'] for p in phases)}")
    if few:
        lines.append(f"Atenção: {len(few)} etapa(s) com menos de 20 quadros da mão (resultado frágil).")
    for key, res in result["comparisons"].items():
        air, motion = key.split("/")
        lines.append("")
        lines.append(f"Encostado × {NAMES[air]} ({NAMES[motion]})")
        lines.append(f"  {'sinal':<20}{'separação':>10}  {'encostado é':<12}{'rodadas':>8}  "
                     f"{'média enc.':>11}{'média ar':>10}")
        for f, r in sorted(res.items(), key=lambda kv: -kv[1]["auc"]):
            mark = "  ← promissor" if r["useful"] else ""
            lines.append(f"  {f:<20}{r['auc']:>10.2f}  {r['touch_is']:<12}"
                         f"{r['rounds_agree']:>4}/{r['rounds']:<3}  "
                         f"{r['touch_mean']:>11.3f}{r['air_mean']:>10.3f}{mark}")
    useful = sorted(f for f, r in result["comparisons"].get("air2/todos", {}).items() if r["useful"])
    lines.append("")
    if useful:
        lines.append(f"Conclusão: separam encostado de ~2 cm: {', '.join(useful)}. "
                     "Próximo passo: testar um detector de toque com esses sinais.")
    else:
        lines.append("Conclusão: nenhum sinal separa encostado de ~2 cm com segurança "
                     f"(separação ≥ {USEFUL_AUC} e todas as rodadas coerentes). "
                     "A caneta continua descendo pela pose; alternativas: sombra (projetor) ou 2ª câmera rasante.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("session", nargs="?", type=Path)
    parser.add_argument("recording", nargs="?", type=Path)
    parser.add_argument("--json", action="store_true", help="saída em JSON")
    args = parser.parse_args(argv)
    session = args.session or latest_session()
    if session is None:
        print("Nenhuma sessão com o estudo do toque em logs/. Na lousa, aperte T.", file=sys.stderr)
        return 1
    _, recording_name = read_phases(session)
    recording = args.recording or (session.parent / recording_name if recording_name else None)
    if recording is None or not recording.exists():
        print(f"Gravação dos pontos da mão não encontrada ({recording_name}).", file=sys.stderr)
        return 1
    try:
        result = analyze(session, recording)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Sessão: {session.name} · gravação: {recording.name}")
    print(json.dumps(result, ensure_ascii=False, indent=1) if args.json else format_report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
