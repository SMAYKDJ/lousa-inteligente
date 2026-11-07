#!/usr/bin/env bash
# SmartBoard Classroom — etapa 1.0 no macOS
# Cria o .venv com Python 3.11 (D009), instala as dependências e baixa o modelo da mão (D006).
# Pode ser executado mais de uma vez: reaproveita o que já existe.

set -euo pipefail
cd "$(dirname "$0")/.."

# O Qt não abre janelas quando o projeto está em pasta protegida do macOS (D011).
case "$(pwd -P)" in
  "$HOME/Desktop"*|"$HOME/Documents"*|"$HOME/Downloads"*)
    echo "ERRO: o projeto está em $(pwd -P)." >&2
    echo "Mesa, Documentos e Downloads são pastas protegidas do macOS e impedem a janela de abrir." >&2
    echo "Mova o projeto (ex.: mv \"$(pwd -P)\" ~/Projetos/) e rode este script de novo." >&2
    exit 1
    ;;
esac

PYTHON_BIN="python3.11"
MODEL_PATH="mobile/vendor/models/hand_landmarker.task"
MODEL_URL="https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"

echo "=== 1/4 Ambiente virtual (.venv) ==="
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERRO: $PYTHON_BIN não encontrado." >&2
  exit 1
fi
if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv
  echo ".venv criado com $("$PYTHON_BIN" --version)"
else
  echo ".venv já existe: $(.venv/bin/python --version)"
fi

echo
echo "=== 2/4 Dependências ==="
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip freeze > requirements.lock.txt
echo "Versões exatas salvas em requirements.lock.txt"

echo
echo "=== 3/4 Verificação das bibliotecas ==="
.venv/bin/python -c "import sys, aiohttp, cryptography, PySide6, pytest; print('python', sys.version.split()[0], '| aiohttp', aiohttp.__version__, '| cryptography', cryptography.__version__, '| PySide6', PySide6.__version__, '| pytest', pytest.__version__)"
.venv/bin/python -c "import mediapipe, cv2, numpy; print('mediapipe', mediapipe.__version__, '| opencv', cv2.__version__, '| numpy', numpy.__version__)"

echo
echo "=== 4/4 Modelo hand_landmarker.task ==="
mkdir -p "$(dirname "$MODEL_PATH")"
if [ ! -s "$MODEL_PATH" ]; then
  curl -fL -o "$MODEL_PATH" "$MODEL_URL"
else
  echo "Modelo já existe, download ignorado."
fi
ls -l "$MODEL_PATH"
shasum -a 256 "$MODEL_PATH"

echo
echo "Etapa 1.0 concluída no Mac. Envie toda esta saída ao Claude."
