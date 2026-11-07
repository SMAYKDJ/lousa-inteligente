// SmartBoard Classroom — captura da câmera do celular.
// Responsabilidade: abrir a câmera traseira e informar a resolução real.
// Nenhuma imagem é gravada ou enviada pela rede (CLAUDE.md §11).

export class CameraError extends Error {}

/** True se o navegador permite a câmera nesta página (exige HTTPS ou localhost). */
export function cameraAvailable() {
  return window.isSecureContext && !!navigator.mediaDevices?.getUserMedia;
}

/**
 * Abre a câmera traseira (preferência, não exigência) e liga ao <video>.
 * @param {HTMLVideoElement} video
 * @param {{width?: number, height?: number}} [size] resolução pedida (o navegador pode ajustar)
 * @returns {Promise<{stream: MediaStream, width: number, height: number, facing: string}>}
 */
export async function openRearCamera(video, { width = 1280, height = 720 } = {}) {
  if (!window.isSecureContext) {
    throw new CameraError("Página fora de contexto seguro (HTTPS). O navegador bloqueia a câmera.");
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new CameraError("Este navegador não oferece acesso à câmera.");
  }

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: width },
        height: { ideal: height },
      },
    });
  } catch (err) {
    const reasons = {
      NotAllowedError: "Permissão da câmera negada. Libere nas configurações do navegador.",
      NotFoundError: "Nenhuma câmera encontrada.",
      NotReadableError: "A câmera está em uso por outro aplicativo.",
    };
    throw new CameraError(reasons[err.name] ?? `Falha ao abrir a câmera: ${err.name ?? err}`);
  }

  video.srcObject = stream;
  await video.play();

  const settings = stream.getVideoTracks()[0]?.getSettings() ?? {};
  return {
    stream,
    width: settings.width || video.videoWidth,
    height: settings.height || video.videoHeight,
    // Webcams de notebook e alguns Android não informam facingMode.
    facing: ["user", "environment"].includes(settings.facingMode) ? settings.facingMode : "unknown",
  };
}

export function closeCamera(stream) {
  stream?.getTracks().forEach((track) => track.stop());
}
