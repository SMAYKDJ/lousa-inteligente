#!/usr/bin/env bash
# SmartBoard Classroom — verificação do ambiente (macOS)
# Apenas lê informações; não instala nem altera nada.

echo "=== Sistema ==="
sw_vers 2>/dev/null || uname -a
echo "Arquitetura: $(uname -m)"

echo
echo "=== Python ==="
for py in python3 python3.13 python3.12 python3.11 python3.10; do
  if command -v "$py" >/dev/null 2>&1; then
    echo "$py -> $(command -v "$py") : $("$py" --version 2>&1)"
  fi
done

echo
echo "=== Bibliotecas relevantes (python3) ==="
python3 - <<'EOF' 2>/dev/null
import importlib
for mod in ["aiohttp", "cryptography", "PySide6", "cv2", "numpy", "pytest", "websockets"]:
    try:
        m = importlib.import_module(mod)
        print(f"{mod}: {getattr(m, '__version__', 'instalado')}")
    except Exception:
        print(f"{mod}: não instalado")
EOF

echo
echo "=== Ferramentas ==="
for tool in pip3 node npm openssl git; do
  if command -v "$tool" >/dev/null 2>&1; then
    echo "$tool: $("$tool" --version 2>&1 | head -n1)"
  else
    echo "$tool: não encontrado"
  fi
done

echo
echo "=== Rede ==="
for iface in en0 en1; do
  ip=$(ipconfig getifaddr "$iface" 2>/dev/null)
  [ -n "$ip" ] && echo "IP ($iface): $ip"
done
echo "Wi-Fi: $(networksetup -getairportnetwork en0 2>/dev/null)"

echo
echo "=== Firewall do macOS ==="
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate 2>/dev/null || echo "não foi possível ler"
