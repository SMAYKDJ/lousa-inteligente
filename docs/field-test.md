# Roteiro do teste real (Fase 7)

Tudo o que está implementado e ainda não foi validado com o equipamento, **em ordem**: cada bloco usa o que o anterior validou. Uma sessão de ~40 min cobre os blocos 1–8; os blocos 9–11 pedem a sala de aula.

Ao fim de cada sessão: `.venv/bin/python -m tools.log_summary` (ou me peça para ler o log). Nada aqui grava imagem: só eventos e, nos blocos 7 e 9, os pontos da mão.

| # | O que testar | Como | Confirma no log | Decisão |
|---|---|---|---|---|
| 1 | Abrir com dois cliques + QR | `SmartBoard.command`; ler o QR com o celular | `connection` conectado | D025 |
| 2 | Calibração automática | 1ª abertura: 1 toque no centro; fechar e reabrir sem mexer o celular: nenhum toque; mexer o celular e reabrir: 1 toque; depois V mede a precisão | `calibration_done mode=markers`, `calibration_reused` | D034 |
| 2b | Assistente completo | A: cantos → V → G → V | `guided_done` | D023 |
| 3 | Cantos discretos | após calibrar, somem em ~1 s; N mostra/esconde | `marker_reference ok`, `mean_side_px` ~19 | D028 |
| 4 | Celular mexido | empurrar o celular: cantos voltam e somem; andar na frente e trocar slide: **não** voltam | `phone_moved`, `phone_reframed` | D030 |
| 5 | Caneta e gestos | escrever, apontar relaxado, mão aberta; L (laboratório) | `lab_done`; linha "Caneta" | D026, D022 |
| 6 | Pinça × indicador | K; escrever o mesmo texto nos dois modos | linha "Caneta" por modo | D021 |
| 7 | Ferramentas e estilo | cores/espessuras, borracha, formas, Selecionar: segurando com o indicador, lados movem e mão perto da câmera amplia / da lousa reduz; abrir a mão solta; 1 s confirma | `ui_style`, `draw_resize signal=size` | 4.4, D035 |
| 7b | Formas à mão | com o Pincel: círculo, retângulo, linha, e letras (O, S, l); Voltar devolve o traço | `draw_snap` | D033 |
| 8 | Gestos de movimento | deslizar ← →; toque de pinça; duas mãos no desenho selecionado | `motion_swipe`, `motion_tap`, zoom | D024 |
| 9 | Slides em tela cheia | PowerPoint, Keynote e Impress: troca de slide e anotações por slide | `slide_change` | 6.2 |
| 10 | Guardar, recuperar, PDF, preferências | escrever; Q; reabrir; O; botão **Salvar PDF**; a barra volta onde estava | `annotations_*`; `preferencias.json` | D027, D031 |
| 11 | Estudo do toque | T (2 min); depois `python -m tools.touch_report` | `touch_phase` ×15 | D029 |
| 12 | Ângulos e paralaxe | V com o celular de frente, ~30° e ~45°; dedo encostado × ~2 cm × ~5 cm | `verify_result` por ângulo | 2.5 |
| 13 | Sala de aula | distâncias, luz, projetor × TV, 45 min de aula | fps, latência, CPU/memória (`log_summary`) | Fase 7 |
| 14 | Windows | `SmartBoard.bat` no notebook do professor | igual ao 1–10 | 1.7 |

**Critério de produto pronto** (CLAUDE.md §18): cada linha com resultado registrado em `docs/testing.md` e os problemas encontrados corrigidos ou documentados.
