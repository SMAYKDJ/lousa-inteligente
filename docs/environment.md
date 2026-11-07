# Ambiente de desenvolvimento

Registro da verificação do ambiente (`CLAUDE.md` §17, itens 3–5).
Data da verificação: 2026-11-06.

## 1. O que foi confirmado

| Item | Resultado | Como foi verificado |
|---|---|---|
| Sistema operacional | macOS (`darwin`) | Informações do dispositivo pelo app Claude |
| Arquitetura | Apple Silicon (`arm64`) | Informações do dispositivo pelo app Claude |
| Pasta do projeto | `~/Projetos/smartboard-classroom` (até 2026-11-06 estava em `~/Desktop`; movida pela D011) | Pasta conectada à sessão |

### 1.1. Plataformas de teste (definidas pelo usuário em 2026-11-06)

| Papel | Equipamento | Uso |
|---|---|---|
| Celular (câmera) | **Android** | Celular de referência para toda a Fase 1 |
| Notebook — desenvolvimento e 1º teste | **macOS** (este Mac, Apple Silicon) | Etapas 1.0 a 1.6 |
| Notebook — destino em sala de aula | **Windows** (notebook do professor) | Validação na etapa 1.7, antes de qualquer uso em aula |

Ver decisão D008 em `decisions.md`.

## 2. O que ainda NÃO foi verificado

O Claude não tem um terminal no macOS. A sessão só consegue ler e escrever arquivos na pasta do projeto. Por isso, os itens abaixo ainda **não foram verificados** e não devem ser tratados como confirmados:

- Versão do Python instalada e qual executável `python3` é usado.
- Bibliotecas já instaladas.
- Endereço IP do notebook na rede Wi-Fi.
- Estado do firewall do macOS.
- Modelo e sistema do celular que será usado nos testes.

Para verificar, execute no Terminal, dentro da pasta do projeto:

```bash
bash scripts/check_env.sh
```

Cole a saída aqui (seção 4) ou envie ao Claude.

No notebook Windows (etapa 1.7), use o equivalente em PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1
```

## 3. Requisitos mínimos para a Fase 1

| Requisito | Motivo |
|---|---|
| Python 3.11 no `.venv` | Mesma versão no Mac e no Windows (D009). |
| Ambiente virtual (`.venv`) | Isolar as dependências do projeto. |
| Celular e notebook na **mesma rede**, sem isolamento de clientes | O celular precisa alcançar o IP do notebook. Redes de escolas costumam bloquear isso (ver risco R3 em `architecture.md`). |
| Permissão de entrada no firewall do macOS para o Python | O macOS pergunta na primeira vez que o servidor abre a porta. |
| Internet **uma única vez**, na preparação | Para baixar o MediaPipe e o modelo para `mobile/vendor/`. Depois disso, tudo funciona sem internet. |

## 4. Resultado do `check_env.sh` (macOS, 2026-11-06)

| Item | Resultado | Observação |
|---|---|---|
| Sistema | macOS 26.5.2 (build 25F84), arm64 | — |
| `python3` padrão | **3.15.0** (Homebrew, `/opt/homebrew/bin/python3`) | Não será usado no projeto (ver D009) |
| Outros Pythons | 3.11.18 (Homebrew), 3.10.21 (`~/.local/bin`) | **3.11** escolhido para o `.venv` (D009) |
| aiohttp, PySide6, pytest | não instalados | Instalar no `.venv` (etapa 1.0) |
| cryptography | 50.0.2 (no Python 3.15 global) | Instalar de novo no `.venv` |
| websockets | 17.2 (global) | Não será usado (D003) |
| cv2, numpy | não instalados | Só na Fase 2 |
| node / npm | 26.10.0 / 11.19.1 | Não é necessário para rodar o projeto |
| openssl | 4.0.3 | Não é necessário: o certificado será gerado pela `cryptography` (D004) |
| git | 2.50.1 | — |
| IP local (en0) | 192.168.1.74 | Endereço que o celular vai acessar. Pode mudar entre redes. |
| Wi-Fi (`networksetup`) | "not associated" | Contradiz o IP ativo em en0. Versões recentes do macOS podem esconder o nome da rede por privacidade, então isso **não** indica que o Wi-Fi esteja desligado. Não confirmado. |
| Firewall do macOS | **desativado** | Nenhum bloqueio esperado no Mac. No Windows (etapa 1.7) o firewall provavelmente estará ativo. |

## 5. Preparação do `.venv` (etapa 1.0)

Comandos a executar no Terminal do Mac, dentro da pasta do projeto:

```bash
cd ~/Projetos/smartboard-classroom
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -c "import aiohttp, cryptography, PySide6; print('aiohttp', aiohttp.__version__, '| cryptography', cryptography.__version__, '| PySide6', PySide6.__version__)"
python -m pip freeze > requirements.lock.txt
```

O `requirements.lock.txt` gerado registra as versões exatas instaladas. As versões principais serão copiadas para o `requirements.txt` (fixação, `CLAUDE.md` §4.4).

**Status:** executada no Mac em 2026-11-06 com `scripts/setup_mac.sh`, sem erros.

| Pacote | Versão instalada |
|---|---|
| Python (.venv) | 3.11.18 |
| aiohttp | 3.14.5 |
| cryptography | 50.0.2 |
| PySide6 | 6.12.0 |
| pytest / pytest-aiohttp | 9.2.0 / 1.1.1 |
| Modelo `hand_landmarker.task` | 7.819.105 bytes, SHA-256 `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1` |

O `.venv` do Mac foi criado com o pacote `PySide6` completo, que inclui o Essentials. Depois da D010, ele continua funcionando sem reinstalar. Instalações novas (o Windows, por exemplo) já recebem só o Essentials.

## 6. Mudança de pasta e recriação do `.venv` (2026-11-06, D011)

O projeto foi movido de `~/Desktop` para `~/Projetos/smartboard-classroom`, porque dentro da Mesa a janela do Qt não abria (diagnóstico em `decisions.md`, D011). O `.venv` foi recriado com `scripts/setup_mac.sh`, sem erros:

| Pacote | Versão |
|---|---|
| Python (.venv) | 3.11.18 |
| aiohttp / cryptography | 3.14.5 / 50.0.2 |
| **PySide6-Essentials** | 6.12.0. Agora só os módulos essenciais (D010); sem WebEngine, PDF e Addons |
| pytest / pytest-aiohttp | 9.2.0 / 1.1.1 |
| Modelo `hand_landmarker.task` | mantido (mesmo SHA-256 `fbc2a300…7cde1`) |

