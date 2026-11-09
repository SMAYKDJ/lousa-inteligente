#!/usr/bin/env bash
# SmartBoard Classroom — abrir com dois cliques no macOS (D025).
#
# Dê dois cliques neste arquivo no Finder. Ele:
#   1. vai para a pasta do projeto;
#   2. instala o que faltar (só quando requirements.txt muda);
#   3. abre a lousa na TV/projetor (--screen auto), sobre a apresentação (--overlay).
# O endereço e o QR code para o celular aparecem na própria lousa.
#
# Na 1ª vez o macOS pode pedir permissão para o Terminal (Acessibilidade, para trocar
# slides; Rede Local, para o celular conectar). Para fechar: Q na janela da câmera ou
# feche esta janela do Terminal.

cd "$(dirname "$0")" || exit 1
echo "SmartBoard Classroom — $(pwd)"

# Evita que configurações Qt herdadas do Homebrew ou de outra instalação
# apontem para plugins incompatíveis antes de o QApplication ser criado.
unset QT_PLUGIN_PATH QT_QPA_PLATFORM_PLUGIN_PATH
export QT_QPA_PLATFORM=cocoa

if [ ! -x .venv/bin/python ]; then
  echo "Primeira vez: preparando o ambiente (pode levar alguns minutos)…"
  bash scripts/setup_mac.sh || { echo "Falhou a preparação. Envie esta tela ao suporte."; read -r -p "Enter para fechar"; exit 1; }
fi

# Instala dependências novas só quando requirements.txt mudou desde a última vez.
stamp=".venv/.requirements.sha256"
current="$(shasum -a 256 requirements.txt | cut -d' ' -f1)"
if [ "$(cat "$stamp" 2>/dev/null)" != "$current" ]; then
  echo "Atualizando dependências…"
  if .venv/bin/python -m pip install -q -r requirements.txt; then
    echo "$current" > "$stamp"
  else
    echo "Aviso: não foi possível atualizar as dependências (sem internet?). Abrindo assim mesmo."
  fi
fi

.venv/bin/python -m desktop.main --overlay --screen auto "$@"
status=$?
if [ $status -ne 0 ]; then
  echo
  echo "A lousa fechou com erro ($status). As mensagens acima ajudam a entender o motivo."
  read -r -p "Enter para fechar"
fi
exit $status
