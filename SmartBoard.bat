@echo off
rem SmartBoard Classroom - abrir com dois cliques no Windows (D025).
rem NAO TESTADO no Windows ainda (etapa 1.7). Usa o Python 3.11 do inicializador "py".
rem Abre a lousa na TV/projetor (--screen auto) sobre a apresentacao (--overlay).
rem O endereco e o QR code para o celular aparecem na propria lousa.
chcp 65001 >nul
cd /d "%~dp0"
echo SmartBoard Classroom - %CD%
if not exist ".venv\Scripts\python.exe" (
  echo Primeira vez: preparando o ambiente, pode levar alguns minutos...
  py -3.11 -m venv .venv || goto erro
  ".venv\Scripts\python.exe" -m pip install --upgrade pip || goto erro
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto erro
)
if not exist "mobile\vendor\models\hand_landmarker.task" (
  echo Baixando o modelo da mao...
  if not exist "mobile\vendor\models" mkdir "mobile\vendor\models"
  powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -OutFile mobile\vendor\models\hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task" || goto erro
)
".venv\Scripts\python.exe" -c "import segno" 2>nul || ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
".venv\Scripts\python.exe" -m desktop.main --overlay --screen auto %*
if errorlevel 1 goto erro
exit /b 0
:erro
echo.
echo A lousa fechou com erro. As mensagens acima ajudam a entender o motivo.
pause
exit /b 1
