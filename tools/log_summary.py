"""Resumo dos logs de sessão (logs/*.jsonl) em tabela, uma linha por conexão.

Uso, na pasta do projeto:

    .venv/bin/python -m tools.log_summary               # log mais recente
    .venv/bin/python -m tools.log_summary logs/session-20261106-153000.jsonl

Cada conexão do celular (hello → desconexão) vira uma linha. Há uma tabela
por modo (D013):
- stream (padrão): quadros enviados pelo celular e processados no notebook;
- local: MediaPipe no celular (câmera, delegate, carga, FPS, ms/quadro).
Serve para comparar variantes (ex.: &side=480&q=0.6, &mode=local&res=480).
"""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from desktop import config


@dataclass
class Segment:
    start_t: str
    client: str = "?"
    camera: str = "?"
    delegate: str | None = None
    load_ms: float | None = None
    fps_hand: list[float] = field(default_factory=list)
    infer_hand: list[float] = field(default_factory=list)
    fps_all: list[float] = field(default_factory=list)
    infer_all: list[float] = field(default_factory=list)
    rtts: list[float] = field(default_factory=list)
    status_count: int = 0
    with_hand: int = 0
    end_reason: str = "—"
    mode: str = "local"  # status sem `mode` vem de clientes antigos (modo local)
    # Modo stream (D013): lado do celular...
    sent_fps: list[float] = field(default_factory=list)
    frame_kb: list[float] = field(default_factory=list)
    encode_ms: list[float] = field(default_factory=list)
    skipped: int = 0
    # ...e lado do notebook (eventos `vision`, um por segundo).
    vision_fps: list[float] = field(default_factory=list)
    vision_ms: list[float] = field(default_factory=list)
    wait_ms: list[float] = field(default_factory=list)
    received: int = 0
    processed: int = 0
    dropped: int = 0
    vision_with_hand: int = 0
    frame_size: str = "—"
    two_hands: int = 0
    to_arrival: list[float] = field(default_factory=list)
    to_result: list[float] = field(default_factory=list)
    clock_uncertainty: list[float] = field(default_factory=list)
    encoder: str = "main"  # clientes até 0.3.x não informam: geravam na página


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _p90(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.9 * (len(ordered) - 1))))]


def read_segments(path: Path) -> list[Segment]:
    segments: list[Segment] = []
    current: Segment | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        event = rec.get("event")
        if event == "hello":
            current = Segment(start_t=rec["t"][11:19], client=rec.get("client", "?"),
                              camera=f'{rec.get("camera_width")}×{rec.get("camera_height")}')
            segments.append(current)
        elif current is None:
            continue
        elif event == "vision":
            current.received += rec.get("received", 0)
            current.processed += rec.get("processed", 0)
            current.dropped += rec.get("dropped", 0)
            current.vision_with_hand += rec.get("with_hand", 0)
            current.two_hands += rec.get("two_hands", 0)
            if rec.get("processed"):
                current.vision_fps.append(rec["fps"])
            if rec.get("inference_ms") is not None:
                current.vision_ms.append(rec["inference_ms"])
            if rec.get("wait_ms") is not None:
                current.wait_ms.append(rec["wait_ms"])
            if rec.get("width"):
                current.frame_size = f'{rec["width"]}×{rec["height"]}'
            if rec.get("to_result_ms") is not None:
                current.to_result.append(rec["to_result_ms"])
                current.to_arrival.append(rec["to_arrival_ms"])
        elif event == "clock":
            current.clock_uncertainty.append(rec["uncertainty_ms"])
        elif event == "status" and rec.get("mode") == "stream":
            current.mode = "stream"
            current.status_count += 1
            if rec.get("fps"):
                current.sent_fps.append(rec["fps"])
            if rec.get("frame_kb") is not None:
                current.frame_kb.append(rec["frame_kb"])
            if rec.get("encode_ms") is not None:
                current.encode_ms.append(rec["encode_ms"])
            current.skipped += rec.get("skipped") or 0
            current.encoder = rec.get("encoder", current.encoder)
        elif event == "status":
            current.status_count += 1
            current.delegate = rec.get("delegate", current.delegate)
            if rec.get("load_ms") is not None:
                current.load_ms = rec["load_ms"]
            if rec.get("fps"):
                current.fps_all.append(rec["fps"])
            if rec.get("inference_ms") is not None:
                current.infer_all.append(rec["inference_ms"])
            if rec.get("tracking_state") == "tracking_active":
                current.with_hand += 1
                if rec.get("fps"):
                    current.fps_hand.append(rec["fps"])
                if rec.get("inference_ms") is not None:
                    current.infer_hand.append(rec["inference_ms"])
        elif event == "rtt":
            current.rtts.append(rec["rtt_ms"])
        elif event == "connection" and rec.get("state") == "disconnected":
            current.end_reason = rec.get("detail", "—")
            current = None
    return segments


def _fmt(value: float | None, digits: int = 1, unit: str = "") -> str:
    return "—" if value is None else f"{value:.{digits}f}{unit}"


def _pct(part: int, whole: int) -> str:
    return "—" if not whole else f"{100 * part / whole:.0f}%"


def format_stream_table(segments: list[Segment]) -> str:
    header = ("| Início | Câmera | Quadro | Enviados q/s | KB/quadro | JPEG ms | Pulados (celular) "
              "| Processados q/s | MediaPipe ms | Espera ms | Descartados (notebook) "
              "| Com mão | 2 mãos | Captura→chegada ms | Captura→resultado ms (±erro) "
              "| RTT mediana / p90 | Fim |")
    lines = [header, "|" + "---|" * 17]
    for s in segments:
        lines.append(
            f"| {s.start_t} | {s.camera} | {s.frame_size} | {_fmt(_median(s.sent_fps))} "
            f"| {_fmt(_median(s.frame_kb), 0)} | {_fmt(_median(s.encode_ms), 0)} ({s.encoder}) "
            f"| {s.skipped} "
            f"| {_fmt(_median(s.vision_fps))} | {_fmt(_median(s.vision_ms), 0)} "
            f"| {_fmt(_median(s.wait_ms), 1)} | {s.dropped}/{s.received} "
            f"| {_pct(s.vision_with_hand, s.processed)} | {_pct(s.two_hands, s.processed)} "
            f"| {_fmt(_median(s.to_arrival), 0)} "
            f"| {_fmt(_median(s.to_result), 0)} (±{_fmt(_median(s.clock_uncertainty), 0)}) "
            f"| {_fmt(_median(s.rtts))} / {_fmt(_p90(s.rtts))} ms | {s.end_reason} |"
        )
    return "\n".join(lines)


def format_table(segments: list[Segment]) -> str:
    header = ("| Início | Câmera | Delegate | Carga | FPS c/ mão (mediana) | ms/quadro c/ mão "
              "| FPS geral | ms/quadro geral | RTT mediana / p90 | s c/ mão | Fim |")
    lines = [header, "|" + "---|" * 11]
    for s in segments:
        load = None if s.load_ms is None else s.load_ms / 1000
        lines.append(
            f"| {s.start_t} | {s.camera} | {s.delegate or '—'} | {_fmt(load, 1, ' s')} "
            f"| {_fmt(_median(s.fps_hand))} | {_fmt(_median(s.infer_hand), 0)} "
            f"| {_fmt(_median(s.fps_all))} | {_fmt(_median(s.infer_all), 0)} "
            f"| {_fmt(_median(s.rtts))} / {_fmt(_p90(s.rtts))} ms "
            f"| {s.with_hand}/{s.status_count} | {s.end_reason} |"
        )
    return "\n".join(lines)


def format_report(segments: list[Segment]) -> str:
    stream = [s for s in segments if s.mode == "stream"]
    local = [s for s in segments if s.mode != "stream"]
    parts = []
    if stream:
        parts += ["Modo stream (MediaPipe no notebook):", format_stream_table(stream)]
    if local:
        parts += ["Modo local (MediaPipe no celular):", format_table(local)]
    return "\n\n".join(parts) if parts else "Nenhuma conexão de celular no log."


def marker_summary(path: Path) -> str | None:
    """Resumo dos marcadores ArUco (D015) e da correção de movimento no log."""
    checks, seen, sides, moves, refs = 0, {}, [], [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("event") == "markers":
            checks += rec["checks"]
            for k, v in rec.get("seen", {}).items():
                seen[k] = seen.get(k, 0) + v
            if rec.get("mean_side_px") is not None:
                sides.append(rec["mean_side_px"])
        elif rec.get("event") == "camera_moved":
            moves.append(rec["shift"])
        elif rec.get("event") == "marker_reference":
            refs.append("ok" if rec.get("ok") else "falhou")
    if not checks:
        return None
    rates = ", ".join(f"id {k}: {100 * seen.get(k, 0) / checks:.0f}%" for k in ("0", "1", "2", "3"))
    side = f"{statistics.median(sides):.0f} px" if sides else "—"
    move = f"{len(moves)} registros, máx {100 * max(moves):.1f}%" if moves else "nenhum"
    return (f"Marcadores: {checks} verificações · vistos {rates} · lado mediano {side} na câmera"
            f" · referência: {', '.join(refs) or '—'} · câmera movida: {move}")


def drawing_summary(path: Path) -> str | None:
    """Resumo do uso das ferramentas (Fase 4): traços, formas, borracha, desfazer, limpar."""
    counts: dict[str, int] = {}
    stroke_points: list[int] = []
    tools: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        event = rec.get("event", "")
        if event == "draw_stroke":
            stroke_points.append(rec.get("points", 0))
        elif event == "draw_shape":
            event = f"draw_{rec.get('shape')}"
        elif event == "ui_confirm":
            event = f"limpar_{rec.get('answer')}"
        elif event == "ui_tool":
            tools.append(rec.get("tool", "?"))
        elif event == "ui_style":
            tools.append("/".join(str(v) for k, v in rec.items() if k in ("color", "width", "eraser")))
        if event == "slide_change":
            event = "slide_ok" if rec.get("sent") else "slide_falhou"
        if event.startswith(("draw_", "limpar_", "slide_", "motion_")):
            counts[event] = counts.get(event, 0) + 1
    if not counts and not tools:
        return None
    names = {"draw_stroke": "traços", "draw_circle": "círculos", "draw_rectangle": "retângulos",
             "draw_erase": "apagamentos", "draw_move": "movimentos", "draw_resize": "redimensionamentos", "draw_resize_none": "seleções sem mudar o tamanho", "slide_ok": "slides trocados", "motion_swipe": "deslizes", "motion_tap": "toques de pinça",
             "motion_click": "cliques por pinça", "draw_zoom": "zoom com duas mãos", "slide_falhou": "trocas de slide falhas", "draw_undo": "voltar", "draw_redo": "avançar",
             "limpar_yes": "limpar: sim", "limpar_no": "limpar: não", "limpar_timeout": "limpar: sem resposta"}
    parts = [f"{names.get(k, k)} {v}" for k, v in sorted(counts.items())]
    if stroke_points:
        parts.append(f"pontos por traço (mediana) {statistics.median(stroke_points):.0f}")
    return f"Desenho: {' · '.join(parts) or 'nada desenhado'} · ferramentas escolhidas: {', '.join(tools) or '—'}"


def pen_summary(path: Path) -> str | None:
    """Caneta (Fase 5): por modo (indicador × pinça), quantas descidas, quanto duraram e o que levantou."""
    by_mode: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("event") == "pen_up":
            m = by_mode.setdefault(rec.get("mode", "pose"), {"held": [], "why": {}})
            m["held"].append(rec["held_s"])
            m["why"][rec.get("pose")] = m["why"].get(rec.get("pose"), 0) + 1
    if not by_mode:
        return None
    lines = []
    for mode, m in sorted(by_mode.items()):
        held = m["held"]
        short = sum(1 for h in held if h < 0.3)
        why = ", ".join(f"{k} {v}" for k, v in sorted(m["why"].items(), key=lambda kv: -kv[1]))
        name = "pinça" if mode == "pinch" else "indicador"
        lines.append(f"Caneta ({name}): desceu {len(held)} vezes · tempo mediano "
                     f"{statistics.median(held):.2f} s · {short} vezes por menos de 0,3 s "
                     f"({100 * short / len(held):.0f}%) · levantada por: {why}")
    return "\n".join(lines)


def gesture_comparison(path: Path) -> str | None:
    """D022: trocas de pose por minuto do reconhecimento ativo × do outro, nos mesmos quadros
    (só quadros com uma mão na imagem). O tempo vem da taxa real de quadros do log."""
    flips = alt = frames = processed = 0
    window_s = 0.0
    engine = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("event") == "vision" and "pose_flips" in rec:
            flips += rec["pose_flips"]
            alt += rec["pose_alt_flips"]
            frames += rec["one_hand"]
            processed += rec.get("processed", 0)
            window_s += rec.get("window_s", 0.0)
        elif rec.get("event") == "start":
            engine = rec.get("gesture_engine")
    if frames < 30 or not processed or not window_s:
        return None
    fps = processed / window_s
    minutes = frames / fps / 60
    active = "novo (kit)" if engine in (None, "kit") else "antigo"
    other = "antigo" if active == "novo (kit)" else "novo (kit)"
    return (f"Reconhecimento da mão ({frames} quadros com uma mão, ~{minutes:.1f} min a {fps:.0f} qps): "
            f"{active} trocou de pose {flips} vezes ({flips / minutes:.0f}/min) · "
            f"{other} {alt} vezes ({alt / minutes:.0f}/min)")


def latest_log(log_dir: Path = config.LOG_DIR) -> Path | None:
    logs = sorted(log_dir.glob("session-*.jsonl"))
    return logs[-1] if logs else None


def usage_summary(path: Path) -> str:
    """Consumo do programa (D031) e cantos que voltaram com o celular mexido (D030)."""
    cpu, mem, moved, reframed = [], [], 0, []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        ev = rec.get("event")
        if ev == "vision":
            if rec.get("cpu_pct") is not None:
                cpu.append(rec["cpu_pct"])
            if rec.get("rss_peak_mb") is not None:
                mem.append(rec["rss_peak_mb"])
        elif ev == "phone_moved":
            moved += 1
        elif ev == "phone_reframed":
            reframed.append(rec.get("seconds", 0.0))
    lines = []
    if cpu:
        ordered = sorted(cpu)
        p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
        lines.append(f"Consumo: CPU mediana {_median(cpu):.0f}% · p95 {p95:.0f}% (100% = um núcleo)"
                     + (f" · memória (pico) {max(mem):.0f} MB" if mem else ""))
    if moved or reframed:
        lines.append(f"Celular mexido (cantos voltaram sozinhos): {moved}× · reenquadrado {len(reframed)}×"
                     + (f", mediana {_median(reframed):.1f} s" if reframed else ""))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Resumo do log de sessão")
    parser.add_argument("log", nargs="?", type=Path, help="arquivo .jsonl (padrão: o mais recente)")
    args = parser.parse_args()
    path = args.log or latest_log()
    if path is None or not path.exists():
        raise SystemExit(f"Nenhum log encontrado em {config.LOG_DIR}")
    print(f"Log: {path}\n")
    print(format_report(read_segments(path)))
    markers = marker_summary(path)
    if markers:
        print("\n" + markers)
    usage = usage_summary(path)
    if usage:
        print("\n" + usage)
    for line in path.read_text(encoding="utf-8").splitlines():
        if '"lab_done"' in line:
            rec = json.loads(line)
            print("\nLaboratório de gestos (acerto · reação):")
            for r in rec["results"]:
                parts = []
                for engine in ("novo", "antigo"):
                    x = r.get(engine)
                    if x and x.get("hit") is not None:
                        reaction = "—" if x["reaction_s"] is None else f"{x['reaction_s']} s"
                        parts.append(f"{engine} {100 * x['hit']:.0f}% · {reaction}")
                print(f"  {r['target']:9}: " + " | ".join(parts))
        if '"guided_done"' in line or '"guided_cancel"' in line:
            rec = json.loads(line)
            if rec["event"] == "guided_cancel":
                print(f"\nAssistente de calibração: cancelado na etapa {rec.get('step')}")
            else:
                print(f"\nAssistente de calibração: cantos {rec.get('corners_error_px')} px · "
                      f"verificação antes {rec.get('verify_before_px')} px → depois {rec.get('verify_after_px')} px"
                      f" · melhora {rec.get('improvement_pct', '—')}% · correção {rec.get('correction')}")
        if '"verify_result"' in line:
            rec = json.loads(line)
            print(f"\nVerificação (V, 4 pontos entre os do G): mediana {rec['median_px']} px "
                  f"({rec['median_pct']}%), máx {rec['max_px']} px · correção {rec['correction']}")
        if '"residual_update"' in line or '"residual_rejected"' in line:
            rec = json.loads(line)
            if rec["event"] == "residual_update":
                print(f"\nCorreção dos 9 pontos: aplicada, maior ajuste {rec['max_offset_px']} px")
            else:
                print(f"\nCorreção dos 9 pontos: recusada ({rec['reason']})")
    comparison = gesture_comparison(path)
    if comparison:
        print("\n" + comparison)
    pen = pen_summary(path)
    if pen:
        print("\n" + pen)
    drawing = drawing_summary(path)
    if drawing:
        print("\n" + drawing)


if __name__ == "__main__":
    main()
