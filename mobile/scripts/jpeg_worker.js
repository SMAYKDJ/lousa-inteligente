// SmartBoard Classroom — gera o JPEG fora da linha principal da página (etapa 2.0).
//
// Recebe uma ImageBitmap já reduzida (createImageBitmap na página) e devolve
// os bytes do JPEG. A imagem só existe em memória (CLAUDE.md §11).

const supported = typeof OffscreenCanvas !== "undefined"
  && typeof OffscreenCanvas.prototype.convertToBlob === "function";
let canvas = null;
let ctx = null;

self.postMessage({ type: "ready", supported });

self.onmessage = async ({ data }) => {
  const { id, bitmap, quality } = data;
  try {
    if (!canvas || canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
      canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
      ctx = canvas.getContext("2d", { alpha: false });
    }
    ctx.drawImage(bitmap, 0, 0);
    bitmap.close();
    const blob = await canvas.convertToBlob({ type: "image/jpeg", quality });
    const jpeg = await blob.arrayBuffer();
    self.postMessage({ type: "jpeg", id, jpeg }, [jpeg]);
  } catch (err) {
    self.postMessage({ type: "error", id, message: String(err) });
  }
};
