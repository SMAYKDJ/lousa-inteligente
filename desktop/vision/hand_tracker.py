"""MediaPipe Hand Landmarker no notebook (D013).

Responsabilidade (CLAUDE.md §3.1, Visão computacional): receber uma imagem
RGB e devolver o estado da mão com a ponta do indicador em camera_norm.
Não conhece rede, Qt nem coordenadas de tela.

O MediaPipe e o OpenCV são importados só aqui dentro, quando o detector é
criado, para o resto do programa (e dos testes) não depender deles.
"""

from __future__ import annotations

import math

from pathlib import Path
from typing import Any, Protocol, Sequence

from desktop import config
from desktop.communication.message_protocol import Handedness, HandState, IndexTip

#: Índice da ponta do indicador nos 21 landmarks da mão do MediaPipe.
INDEX_TIP = 8

#: Pulso e base dos dedos indicador, médio, anelar e mínimo (MCP).
WRIST = 0
PALM_POINTS = (WRIST, 5, 9, 13, 17)

#: (articulação do meio PIP, ponta) de indicador, médio, anelar e mínimo.
FINGERS = {"index": (6, 8), "middle": (10, 12), "ring": (14, 16), "pinky": (18, 20)}


def finger_ratios(landmarks, width: int, height: int) -> dict[str, float]:
    """Para cada dedo: distância pulso→ponta ÷ distância pulso→PIP (em px).

    > 1 quando o dedo está esticado, < 1 quando dobrado. Não depende da
    rotação da mão nem de qual lado (palma ou costas) a câmera vê.
    """
    w = landmarks[WRIST]

    def dist(p):
        return (((p.x - w.x) * width) ** 2 + ((p.y - w.y) * height) ** 2) ** 0.5

    return {name: dist(landmarks[tip]) / max(dist(landmarks[pip]), 1e-6)
            for name, (pip, tip) in FINGERS.items()}


def classify_pose(ratios: dict[str, float]) -> str:
    """pointing: só o indicador esticado; open: ≥ 3 dedos esticados; fist: nenhum."""
    extended = {k for k, v in ratios.items() if v >= config.FINGER_EXTENDED_RATIO}
    curled = {k for k, v in ratios.items() if v <= config.FINGER_CURLED_RATIO}
    if "index" in extended and {"middle", "ring", "pinky"} <= curled:
        return "pointing"
    if len(extended) >= 3:
        return "open"
    if not extended and len(curled) == 4:
        return "fist"
    return "other"


class HandDetector(Protocol):
    """O que o processador de quadros precisa de um detector de mão."""

    def detect(self, rgb: Any, timestamp_ms: int) -> list[HandState] | HandState: ...

    def close(self) -> None: ...


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def hand_state_from_result(landmarks: Sequence[Sequence[Any]],
                           handedness: Sequence[Sequence[Any]]) -> HandState:
    """Converte a saída do MediaPipe (listas por mão) para HandState.

    `landmarks[0][i]` tem .x .y .z normalizados pela imagem; `handedness[0][0]`
    tem .category_name e .score. Igual ao celular (hand_tracking.js): x e y
    limitados a [0, 1] e o nome da mão como o MediaPipe dá (ele supõe imagem
    espelhada, então com a câmera traseira "Left"/"Right" podem vir trocados).
    """
    if not landmarks:
        return HandState(present=False)
    tip = landmarks[0][INDEX_TIP]
    category = handedness[0][0] if handedness and handedness[0] else None
    name = getattr(category, "category_name", None)
    score = getattr(category, "score", None)
    return HandState(
        present=True,
        handedness=Handedness.LEFT if name == "Left" else Handedness.RIGHT,
        confidence=_clamp01(float(score)) if score is not None else 0.0,
        index_tip=IndexTip(x=_clamp01(float(tip.x)), y=_clamp01(float(tip.y)), z=float(tip.z)),
    )


def palm_size_px(points, width: int, height: int) -> float:
    """Distância média do pulso às bases dos dedos, em px da câmera."""
    wrist = points[0]
    distances = [(((p.x - wrist.x) * width) ** 2 + ((p.y - wrist.y) * height) ** 2) ** 0.5
                 for p in points[1:]]
    return sum(distances) / len(distances)


FINGERTIPS = (4, 8, 12, 16, 20)


def hand_openness(landmarks, width: int, height: int) -> float:
    """Quanto a mão está aberta: distância média pulso→pontas ÷ pulso→base do dedo médio.

    Não depende do tamanho aparente da mão nem da rotação. Mão fechada ≈ 1, aberta ≈ 2.
    Usada para redimensionar com o Selecionar (Fase 4, etapa 4.6).
    """
    def xy(i):
        return landmarks[i].x * width, landmarks[i].y * height
    wx, wy = xy(0)
    mx, my = xy(9)
    palm = math.hypot(mx - wx, my - wy)
    if palm < 1e-6:
        return 0.0
    tips = [math.hypot(xy(i)[0] - wx, xy(i)[1] - wy) for i in FINGERTIPS]
    return sum(tips) / len(tips) / palm


def pinch_ratio(landmarks, width: int, height: int) -> float:
    """Distância ponta do polegar (4) ↔ ponta do indicador (8) ÷ pulso→base do dedo médio.

    Pinça fechada ≈ 0,1–0,3; dedos separados > 0,6. Não depende do tamanho aparente.
    """
    def xy(i):
        return landmarks[i].x * width, landmarks[i].y * height
    wx, wy = xy(0)
    mx, my = xy(9)
    palm = math.hypot(mx - wx, my - wy)
    if palm < 1e-6:
        return 9.9
    (tx, ty), (ix, iy) = xy(4), xy(8)
    return math.hypot(tx - ix, ty - iy) / palm


def hands_from_result(landmarks: Sequence[Sequence[Any]], handedness: Sequence[Sequence[Any]],
                      width: int, height: int, gestures: Sequence[Any] | None = None) -> list[HandState]:
    """Todas as mãos do resultado, com pontos da palma e tamanho aparente.

    `gestures`: resultados do reconhecimento novo (gestures.GestureEngine, D022), um por mão.
    Com config.GESTURE_ENGINE == "kit", a pose e a pinça vêm deles; a pose do outro
    reconhecimento vai em `pose_alt`, para comparar no log.
    """
    hands = []
    for i, hand_landmarks in enumerate(landmarks):
        base = hand_state_from_result([hand_landmarks], handedness[i:i + 1])
        palm = tuple(IndexTip(float(hand_landmarks[j].x), float(hand_landmarks[j].y),
                              float(hand_landmarks[j].z)) for j in PALM_POINTS)
        legacy_pose = classify_pose(finger_ratios(hand_landmarks, width, height))
        legacy_pinch = pinch_ratio(hand_landmarks, width, height)
        g = gestures[i] if gestures is not None and i < len(gestures) else None
        if g is not None and config.GESTURE_ENGINE == "kit":
            pose, pose_alt, pinch = g.board_pose, legacy_pose, g.pinch_gap
        else:
            pose, pose_alt, pinch = legacy_pose, (g.board_pose if g is not None else None), legacy_pinch
        hands.append(HandState(present=True, handedness=base.handedness,
                               confidence=base.confidence, index_tip=base.index_tip,
                               palm=palm, palm_size_px=round(palm_size_px(palm, width, height), 2),
                               pose=pose,
                               openness=round(hand_openness(hand_landmarks, width, height), 3),
                               pinch=round(pinch, 3), pose_alt=pose_alt,
                               landmarks=tuple(IndexTip(float(p.x), float(p.y), float(p.z))
                                               for p in hand_landmarks)))
    return hands


class MediaPipeHandDetector:
    """HandLandmarker em modo VIDEO (usa o quadro anterior para rastrear).

    Deve ser criado e usado na mesma thread (a do processador de quadros).
    """

    def __init__(self, model_path: Path = config.HAND_MODEL_PATH, max_hands: int | None = None) -> None:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import (
            HandLandmarker,
            HandLandmarkerOptions,
            RunningMode,
        )

        if not model_path.is_file():
            raise FileNotFoundError(f"Modelo do MediaPipe não encontrado: {model_path}")
        self._mp = mp
        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=RunningMode.VIDEO,
            num_hands=max_hands or config.MAX_HANDS,
            min_hand_detection_confidence=config.MIN_HAND_DETECTION_CONFIDENCE,
            min_hand_presence_confidence=config.MIN_HAND_PRESENCE_CONFIDENCE,
            min_tracking_confidence=config.MIN_TRACKING_CONFIDENCE,
        )
        self._landmarker = HandLandmarker.create_from_options(options)
        # Reconhecimento com filtro nos pontos, forma em 3D e histerese (D022). Tem estado
        # (filtros por mão), por isso vive junto do detector, na thread da visão.
        from desktop.vision.gestures import GestureEngine
        self._gestures = GestureEngine()
        # Gravação só dos pontos da mão (--record, D024): nenhuma imagem é gravada.
        self._recorder = None
        if config.RECORD_LANDMARKS_PATH is not None:
            from desktop.vision.landmark_recorder import LandmarkRecorder
            self._recorder = LandmarkRecorder(Path(config.RECORD_LANDMARKS_PATH))

    def detect(self, rgb: Any, timestamp_ms: int) -> list[HandState]:
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, timestamp_ms)
        width, height = rgb.shape[1], rgb.shape[0]
        world = getattr(result, "hand_world_landmarks", None) or []
        hands = []
        for i, lm in enumerate(result.hand_landmarks):
            wl = world[i] if i < len(world) else None
            label = result.handedness[i][0].category_name if result.handedness[i] else "Right"
            hands.append(([(p.x, p.y, p.z) for p in lm],
                          [(p.x, p.y, p.z) for p in wl] if wl else None, label))
        if self._recorder is None and config.RECORD_LANDMARKS_PATH is not None:
            # Ligada no meio da sessão (estudo do toque, tecla T).
            from desktop.vision.landmark_recorder import LandmarkRecorder
            self._recorder = LandmarkRecorder(Path(config.RECORD_LANDMARKS_PATH))
        if self._recorder is not None:
            self._recorder.write(timestamp_ms, width / max(height, 1), hands)
        gestures = self._gestures.update(hands, timestamp_ms / 1000, width / max(height, 1))
        return hands_from_result(result.hand_landmarks, result.handedness, width, height, gestures)

    def close(self) -> None:
        self._landmarker.close()
        if self._recorder is not None:
            self._recorder.close()


def decode_jpeg_rgb(jpeg: bytes) -> Any:
    """JPEG → matriz RGB (altura × largura × 3, uint8). None se inválido."""
    import cv2
    import numpy as np

    bgr = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
