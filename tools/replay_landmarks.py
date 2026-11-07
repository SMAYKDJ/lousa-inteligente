"""Reproduz uma gravação dos pontos da mão (--record) sem câmera (D024).

Roda o reconhecimento novo (D022) e o antigo (D018) sobre os mesmos quadros e
mostra, para cada um: trocas de pose por minuto, tempo em cada pose e quantas
"piscadas" (pose que dura menos de 0,2 s). Opcionalmente, testa outros limiares
do reconhecimento novo, para ajustar com dados reais.

Uso:
  python -m tools.replay_landmarks                       # gravação mais recente em logs/
  python -m tools.replay_landmarks logs/landmarks-….jsonl.gz
  python -m tools.replay_landmarks --enter 0.55 --exit 0.35 --debounce 0.1
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from desktop import config
from desktop.vision.gestures import GestureEngine
from desktop.vision.hand_tracker import classify_pose, finger_ratios
from desktop.vision.landmark_recorder import read_recording
from desktop.vision.synthetic_hands import as_landmarks

BLINK_S = 0.2


def latest_recording(directory: Path = config.LOG_DIR) -> Path | None:
    files = sorted(directory.glob("landmarks-*.jsonl.gz"))
    return files[-1] if files else None


def analyze(path: Path) -> dict:
    """Linha do tempo da 1ª mão (quadros com exatamente uma mão), novo × antigo."""
    engine = GestureEngine()
    timeline: dict[str, list[tuple[float, str]]] = {"novo": [], "antigo": []}
    frames = 0
    t_first = t_last = None
    for t, aspect, hands in read_recording(path):
        results = engine.update(hands, t, aspect)
        if len(hands) != 1:
            continue
        frames += 1
        t_first = t if t_first is None else t_first
        t_last = t
        img, _, _ = hands[0]
        width, height = 640, round(640 / aspect)
        timeline["novo"].append((t, results[0].board_pose))
        timeline["antigo"].append((t, classify_pose(finger_ratios(as_landmarks(img), width, height))))
    duration = (t_last - t_first) if frames > 1 else 0.0
    out = {"frames": frames, "duration_s": duration}
    for name, tl in timeline.items():
        flips, blinks, time_in = 0, 0, Counter()
        start = tl[0][0] if tl else 0.0
        for (t0, p0), (t1, p1) in zip(tl, tl[1:]):
            time_in[p0] += t1 - t0
            if p1 != p0:
                flips += 1
                if t1 - start < BLINK_S:
                    blinks += 1
                start = t1
        minutes = max(duration / 60, 1e-9)
        out[name] = {"flips": flips, "flips_per_min": flips / minutes, "blinks": blinks,
                     "time": {k: v / max(duration, 1e-9) for k, v in time_in.items()}}
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--enter", type=float, help=f"nota para entrar na pose (atual {config.GESTURE_ENTER})")
    parser.add_argument("--exit", type=float, help=f"nota para sair (atual {config.GESTURE_EXIT})")
    parser.add_argument("--debounce", type=float, help=f"confirmação em s (atual {config.GESTURE_DEBOUNCE_S})")
    args = parser.parse_args(argv)
    path = args.path or latest_recording()
    if path is None or not path.is_file():
        print("Nenhuma gravação. Rode o programa com --record.", file=sys.stderr)
        return 1
    if args.enter is not None:
        config.GESTURE_ENTER = args.enter
    if args.exit is not None:
        config.GESTURE_EXIT = args.exit
    if args.debounce is not None:
        config.GESTURE_DEBOUNCE_S = args.debounce
    r = analyze(path)
    print(f"Gravação: {path.name} · {r['frames']} quadros com uma mão · {r['duration_s'] / 60:.1f} min")
    print(f"Limiares do novo: entra {config.GESTURE_ENTER} · sai {config.GESTURE_EXIT} · "
          f"confirma {config.GESTURE_DEBOUNCE_S * 1000:.0f} ms")
    for name in ("novo", "antigo"):
        x = r[name]
        share = ", ".join(f"{k} {100 * v:.0f}%" for k, v in sorted(x["time"].items(), key=lambda kv: -kv[1]))
        print(f"  {name:6}: {x['flips']} trocas ({x['flips_per_min']:.0f}/min), "
              f"{x['blinks']} piscadas (< {BLINK_S * 1000:.0f} ms) · tempo: {share}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
