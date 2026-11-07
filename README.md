# SmartBoard Classroom

## Abrir a lousa (dois cliques)

- **Mac:** dois cliques em `SmartBoard.command` (na pasta do projeto). Para ter à mão: arraste-o para o lado direito do Dock ou crie um atalho na Mesa (⌘⌥ + arrastar).
- **Windows:** dois cliques em `SmartBoard.bat` (ainda não testado).
- A lousa abre na TV/projetor e mostra um **QR code**: aponte a câmera do celular para ele e toque no link.

Lousa branca inteligente de baixo custo: **celular** (câmera + rastreamento da mão) + **notebook** (aplicação e overlay) + **projetor**, conectados por Wi-Fi local.

## Documentos de referência

| Arquivo | Define |
|---|---|
| [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) | **O que** construir — produto, funcionalidades, decisões de experiência aprovadas |
| [`CLAUDE.md`](CLAUDE.md) | **Como** construir — regras de engenharia, testes, proibições, fluxo de trabalho |

Os dois são mantidos separados de propósito: regras de programação não se misturam com requisitos do produto.

## Estrutura

```
smartboard-classroom/
├── CLAUDE.md             # diretrizes de desenvolvimento
├── PROJECT_CONTEXT.md    # especificação do produto
├── README.md
├── requirements.txt
├── docs/                 # arquitetura, decisões, calibração, protocolo, roadmap
├── desktop/              # aplicação Python do notebook
├── mobile/               # página web aberta no navegador do celular
└── tests/                # testes automatizados
```

## Status

Todas as funcionalidades do `PROJECT_CONTEXT.md` (RF01–RF32) estão **implementadas e com testes automatizados**. Validadas no Mac com o celular: rastreamento, calibração, sidebar, ferramentas, seleção/redimensionar e troca de slides pelo navegador. **O resto depende do teste real**, reunido em ordem em [`docs/field-test.md`](docs/field-test.md). Windows (`SmartBoard.bat`) ainda não testado.

## Usar na aula

Na lousa (com a mão): botão circular na borda abre a barra. Ferramentas: Ponteiro, Selecionar (segurando com o indicador: lados movem, mão perto da câmera amplia, perto da lousa reduz; abrir a mão solta), Pincel, Borracha, Círculo, Retângulo, Voltar, Avançar, Limpar, Slide anterior/próximo, **Salvar PDF**, Girar barra, Mover. Deslizar a mão aberta troca o slide. Com o Pincel, um círculo, retângulo ou linha desenhado à mão vira a forma perfeita (Voltar desfaz).

Teclas (na janela da câmera, no notebook):

| Tecla | Faz |
|---|---|
| A | ajuste completo da calibração (cantos → verificação → 9 pontos → verificação). Ao abrir, a lousa se calibra pelos marcadores com 1 toque no centro, ou sem toque se o celular não saiu do lugar |
| C / G / V | só os cantos / teste dos 9 pontos / verificação entre eles |
| R / S / M | correção dos 9 pontos / filtro de suavização / malha (liga e desliga) |
| N | mostra/esconde os marcadores dos cantos |
| K | caneta: indicador esticado ↔ pinça |
| H | gestos de movimento (deslizar, toque de pinça, duas mãos) |
| E / O | salvar PDF das anotações / recuperar a última aula |
| L / T | laboratório de gestos / estudo do toque |
| P / F / Esc / Q | painel / tela cheia / cancelar / sair |

As anotações são salvas sozinhas em `anotacoes/`; posição da barra e estilo do pincel ficam em `preferencias.json`; a calibração, em `calibracao.json`.

## Como rodar (Mac)

```bash
cd ~/Projetos/smartboard-classroom
.venv/bin/python -m pytest                    # testes
.venv/bin/python -m desktop.main              # notebook: janela do cursor + URL para o celular
.venv/bin/python -m desktop.main --screen 1   # janela em tela cheia na 2ª tela (Smart TV / projetor)
.venv/bin/python -m desktop.main --headless   # notebook sem janela (eventos no terminal)
.venv/bin/python -m tools.fake_phone "URL"    # celular simulado (desenvolvimento)
.venv/bin/python -m tools.log_summary         # tabela do último log de sessão (logs/)
```

Primeira instalação ou dependências novas: `bash scripts/setup_mac.sh`.

Na janela: **F** liga e desliga a tela cheia, **P** mostra e esconde o painel, **Q** fecha.

Opções na URL do celular:

- `&mode=local`: MediaPipe no próprio celular.
- `&side=480`: lado maior do JPEG.
- `&q=0.6`: qualidade do JPEG.
- `&fps=20`: teto de envio.

Critério de sucesso da Fase 1: mover o indicador diante da câmera do celular e ver um cursor acompanhando o movimento no notebook em tempo real.

Veja o roteiro completo em [`docs/development-roadmap.md`](docs/development-roadmap.md).
