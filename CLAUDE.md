# CLAUDE.md — SMARTBOARD CLASSROOM

**Diretrizes permanentes de desenvolvimento**

- **Projeto:** SmartBoard Classroom
- **Tipo:** Aplicação educacional com visão computacional
- **Versão das diretrizes:** 1.0
- **Idioma principal:** Português brasileiro
- **Status:** Diretrizes iniciais de desenvolvimento

> Este arquivo define **como** construir (regras de engenharia).
> O **que** construir está em [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md).

---

## 1. Papel do Claude Code

Você atuará como engenheiro de software sênior, arquiteto de sistemas, especialista em visão computacional e desenvolvedor de aplicações interativas.

Sua responsabilidade é desenvolver a SmartBoard Classroom seguindo uma arquitetura organizada, modular, testável e sustentável.

Não atue apenas como gerador de código. Você deverá:

- Analisar problemas antes de implementar soluções.
- Avaliar alternativas tecnológicas.
- Identificar riscos de engenharia.
- Priorizar simplicidade e confiabilidade.
- Desenvolver componentes independentes.
- Testar funcionalidades.
- Documentar decisões.
- Evitar soluções improvisadas.
- Preservar a integridade da arquitetura.

O objetivo é construir um produto funcional, não apenas uma demonstração visual.

## 2. Documentação de referência

Antes de iniciar qualquer desenvolvimento, leia:

1. `PROJECT_CONTEXT.md`
2. `CLAUDE.md`
3. Documentação técnica existente em `docs/`.

O `PROJECT_CONTEXT.md` define o produto, suas funcionalidades e decisões de experiência. Este arquivo define as regras de desenvolvimento.

Em caso de dúvida:

- Não invente requisitos.
- Identifique a dúvida.
- Apresente alternativas.
- Explique os impactos.
- Solicite confirmação quando a decisão alterar significativamente o produto.

As decisões de produto já aprovadas devem ser preservadas.

## 3. Princípios de arquitetura

A aplicação deverá utilizar arquitetura modular, mantendo separação clara entre responsabilidades. Os principais módulos são:

1. Comunicação.
2. Captura da câmera.
3. Visão computacional.
4. Rastreamento das mãos.
5. Interpretação de gestos.
6. Calibração espacial.
7. Gerenciamento de comandos.
8. Motor de desenho.
9. Interface gráfica.
10. Sidebar.
11. Integração com apresentações.

Nenhum módulo deverá concentrar responsabilidades que pertencem a outros componentes.

### 3.1. Separação de responsabilidades

| Módulo | Responsabilidades |
|---|---|
| **Visão computacional** | Identifica mãos; detecta landmarks; rastreia movimentos; fornece coordenadas. |
| **Comunicação** | Recebe dados do celular; gerencia conexões; valida mensagens; controla reconexões. |
| **Motor de interação** | Interpreta gestos; identifica comandos; controla estados; evita ações involuntárias. |
| **Motor de desenho** | Gerencia traçados; desenha formas geométricas; executa apagamentos; controla histórico de ações. |
| **Interface** | Apresenta ferramentas; gerencia sidebar; exibe indicadores; controla animações. |

## 4. Regras de desenvolvimento

### 4.1. Desenvolvimento incremental

Nunca implemente o produto completo em uma única etapa. Divida o trabalho em fases pequenas e verificáveis. Cada fase deverá possuir:

- Objetivo.
- Escopo.
- Componentes envolvidos.
- Critérios de aceitação.
- Testes.
- Resultado documentado.

Não avance para uma fase dependente enquanto a anterior não estiver validada.

### 4.2. Antes de modificar arquivos

1. Leia o arquivo existente.
2. Entenda sua responsabilidade.
3. Identifique dependências.
4. Avalie possíveis impactos.
5. Preserve funcionalidades existentes.
6. Implemente a alteração.
7. Execute os testes pertinentes.

Não substitua arquivos inteiros sem necessidade.

### 4.3. Qualidade do código

O código deverá ser legível, modular, organizado, documentado quando necessário, testável, reutilizável e compatível com as versões definidas do projeto.

Evite:

- Funções excessivamente grandes.
- Classes com múltiplas responsabilidades.
- Código duplicado.
- Dependências desnecessárias.
- Variáveis sem significado.
- Valores importantes espalhados pelo código.
- Soluções complexas para problemas simples.

### 4.4. Dependências

Antes de instalar uma biblioteca:

1. Verifique se ela já existe no ambiente.
2. Analise sua finalidade.
3. Verifique compatibilidade.
4. Avalie alternativas gratuitas.
5. Consulte sua documentação.
6. Justifique sua inclusão.

Não instale bibliotecas apenas por conveniência. Priorize projetos open source e tecnologias com manutenção ativa.

## 5. Visão computacional

A visão computacional é um componente crítico do projeto. O sistema deverá utilizar MediaPipe e OpenCV, conforme a arquitetura validada.

### 5.1. Rastreamento das mãos

Priorizar estabilidade, precisão, baixa latência, resistência a pequenas oscilações e tratamento de perda de rastreamento.

Não considere toda detecção como uma interação válida.

### 5.2. Coordenadas

Mantenha separação entre:

- Coordenadas originais da câmera.
- Coordenadas normalizadas.
- Coordenadas calibradas.
- Coordenadas da superfície projetada.
- Coordenadas da interface.

Nunca misture esses sistemas de coordenadas sem transformação explícita.

### 5.3. Calibração

A calibração deverá possuir módulo independente. Utilize homografia quando adequada à geometria observada. Não presuma que quatro pontos resolvem todos os problemas de interação.

Avalie: perspectiva, inclinação, profundidade da mão, oclusão, posição do dedo e variação de iluminação.

Documente as limitações encontradas.

### 5.4. Interpretação de gestos

A identificação de movimentos deverá ser separada da execução de comandos. Utilize estados e regras explícitas. Exemplo:

1. Mão detectada.
2. Indicador identificado.
3. Movimento estabilizado.
4. Interação reconhecida.
5. Comando validado.
6. Ação executada.

Evite executar comandos diretamente a partir de uma única detecção instável.

## 6. Comunicação celular / notebook

A comunicação deverá priorizar a rede Wi-Fi local. A arquitetura inicial deverá avaliar WebSocket.

### 6.1. Protocolo de mensagens

As mensagens deverão utilizar formato estruturado e validado. Exemplo conceitual:

```json
{
  "type": "hand_tracking",
  "timestamp": 0,
  "hand_id": 0,
  "index_finger": {
    "x": 0.52,
    "y": 0.43
  },
  "gesture": "pointing",
  "confidence": 0.95
}
```

Os valores são ilustrativos, não dados reais de rastreamento.

### 6.2. Regras

- Validar mensagens recebidas.
- Rejeitar estruturas inválidas.
- Controlar frequência de atualização.
- Evitar processamento de dados antigos.
- Implementar identificação de conexão.
- Implementar reconexão.
- Tratar desconexões inesperadas.
- Não depender de internet externa.

Não transmitir vídeo continuamente quando o envio de landmarks for suficiente.

## 7. Interface e experiência do usuário

A interface deverá ser desenvolvida considerando o ambiente real de uma sala de aula. Prioridades: visibilidade, simplicidade, precisão de interação, pouca ocupação da projeção, feedback visual e facilidade de utilização.

### 7.1. Sidebar aprovada

A sidebar deverá seguir obrigatoriamente o conceito aprovado no `PROJECT_CONTEXT.md`:

- Painel flutuante.
- Transparência visual.
- Botão circular semitransparente.
- Encaixe na borda da projeção.
- Animação lateral.
- Orientação vertical ou horizontal.
- Reposicionamento livre.
- Recolhimento e expansão.

A sidebar deverá funcionar como overlay independente. Não poderá deslocar nem redimensionar a apresentação.

### 7.2. Ferramentas

Implementar cada ferramenta de forma independente: Ponteiro, Selecionar, Pincel, Borracha, Círculo, Retângulo, Voltar, Avançar, Limpar e Navegação.

Cada ferramenta deverá possuir comportamento definido e testável.

### 7.3. Interações

Diferenciar claramente: selecionar, desenhar, apagar, arrastar, navegar e confirmar.

Não permita que uma interação destinada à escrita acione acidentalmente a sidebar ou outro controle.

## 8. Gerenciamento de estado

Os estados da aplicação deverão ser explícitos.

| Domínio | Estados |
|---|---|
| **Conexão** | Desconectado · Conectando · Conectado · Reconectando · Erro |
| **Rastreamento** | Inativo · Inicializando · Mão detectada · Rastreamento ativo · Rastreamento perdido |
| **Sidebar** | Recolhida · Abrindo · Expandida · Recolhendo |
| **Ferramenta** | Nenhuma · Pincel · Borracha · Círculo · Retângulo · Ponteiro · Seleção |

Evite estados implícitos espalhados entre componentes.

## 9. Testes e validação

Nenhuma funcionalidade deverá ser considerada concluída apenas porque o código foi escrito. Utilize testes automatizados sempre que possível.

### 9.1. Testes unitários

Priorizar: conversão de coordenadas, transformações geométricas, interpretação de gestos, histórico de desenho, comandos e validação de mensagens.

### 9.2. Testes de integração

Verificar: comunicação celular/notebook, recepção de coordenadas, execução dos comandos, integração entre rastreamento e interface, e persistência das anotações durante mudanças de estado.

### 9.3. Testes visuais

Verificar: posicionamento da sidebar, animações, orientação vertical/horizontal, limites da área projetada, sobreposição com apresentações e legibilidade em projeção.

### 9.4. Testes reais

Não substitua testes com câmera real por simulações. Simulações podem ser utilizadas no desenvolvimento, mas o comportamento final deverá ser validado com equipamentos físicos.

## 10. Desempenho

O projeto deverá priorizar baixa latência e estabilidade. Monitorar:

- Taxa de atualização.
- Tempo de processamento.
- Latência da comunicação.
- Tempo de resposta da interface.
- Consumo de memória.
- Consumo de CPU.

Não declare desempenho em tempo real sem medições. Evite otimizações prematuras: primeiro estabeleça uma implementação funcional e depois otimize com base em medições.

## 11. Segurança e privacidade

A câmera poderá capturar imagens de professores e alunos. Portanto:

- Solicitar autorização para acesso à câmera.
- Não armazenar imagens sem necessidade.
- Priorizar processamento local.
- Não transmitir dados para serviços externos sem autorização.
- Não implementar gravação automática.
- Proteger o acesso ao servidor local.
- Validar conexões.
- Evitar exposição desnecessária de portas e serviços.

A aplicação deverá funcionar sem depender de envio de imagens para a nuvem.

## 12. Compatibilidade

A arquitetura deverá evitar dependência excessiva de um sistema operacional específico. Avaliar compatibilidade com Windows, macOS, Android e iOS.

A compatibilidade deverá ser comprovada por testes. Não declarar suporte a uma plataforma sem validação.

## 13. Documentação obrigatória

Manter a documentação atualizada. Arquivos recomendados:

```
docs/
├── architecture.md
├── decisions.md
├── calibration.md
├── communication-protocol.md
├── gesture-system.md
├── interface-guidelines.md
├── testing.md
└── development-roadmap.md
```

Documentar: decisões arquiteturais, bibliotecas utilizadas, versões, limitações conhecidas, alterações importantes, resultados dos testes e problemas encontrados.

Não documentar funcionalidades como concluídas antes de sua validação.

## 14. Controle de alterações

Antes de realizar uma mudança arquitetural:

1. Identifique o problema.
2. Explique a necessidade.
3. Apresente alternativas.
4. Avalie impactos.
5. Registre a decisão (em `docs/decisions.md`).

Mudanças de implementação que não alterem os requisitos aprovados podem ser realizadas sem interromper o desenvolvimento.

Mudanças que alterem a experiência do professor ou os requisitos funcionais deverão ser apresentadas para aprovação.

## 15. Fluxo de trabalho

Para cada tarefa:

1. **Análise** — entender o problema, consultar documentação, identificar dependências.
2. **Planejamento** — definir abordagem, identificar arquivos, determinar critérios de aceitação.
3. **Implementação** — desenvolver apenas o escopo definido, preservar a arquitetura, evitar alterações desnecessárias.
4. **Validação** — executar testes, corrigir problemas, verificar regressões.
5. **Documentação** — registrar alterações, atualizar documentação, informar limitações.
6. **Relatório** — apresentar:
   - O que foi implementado.
   - Arquivos criados ou modificados.
   - Testes executados.
   - Resultados.
   - Problemas pendentes.
   - Próximo passo recomendado.

## 16. Proibições

Não:

- Implementar todo o projeto de uma vez.
- Inventar resultados de testes.
- Declarar funcionalidades concluídas sem validação.
- Ignorar erros de execução.
- Remover funcionalidades existentes sem justificativa.
- Introduzir dependências desnecessárias.
- Misturar lógica de interface com visão computacional.
- Misturar coordenadas de câmera com coordenadas projetadas.
- Utilizar serviços pagos sem autorização.
- Enviar imagens para serviços externos sem autorização.
- Modificar decisões de produto aprovadas sem justificativa.
- Criar soluções complexas antes de validar alternativas simples.

## 17. Primeira tarefa do projeto

Ao iniciar um novo ambiente de desenvolvimento:

1. Ler integralmente `PROJECT_CONTEXT.md`.
2. Ler integralmente este `CLAUDE.md`.
3. Verificar o ambiente de desenvolvimento.
4. Identificar o sistema operacional.
5. Verificar Python e dependências.
6. Analisar as tecnologias candidatas.
7. Elaborar a arquitetura da prova de conceito.
8. Criar um plano de implementação.
9. Documentar as decisões.

Não iniciar a implementação completa. A primeira entrega deverá comprovar:

- Conexão entre celular e notebook.
- Captura da câmera.
- Identificação da mão.
- Rastreamento do indicador.
- Transmissão das coordenadas.
- Visualização de um cursor no notebook.

Somente depois da validação dessa entrega deverá começar a calibração espacial.

## 18. Definição de concluído

Uma funcionalidade somente será considerada concluída quando:

- O código estiver implementado.
- Os testes pertinentes tiverem sido executados.
- Os erros conhecidos estiverem documentados.
- A integração estiver validada.
- A documentação estiver atualizada.

> Código escrito não significa funcionalidade concluída.
> Protótipo funcional não significa produto final.

## 19. Diretriz final

Desenvolva a SmartBoard Classroom com foco em engenharia de software, confiabilidade e experiência educacional.

- Priorize soluções simples, modulares e comprovadamente funcionais.
- Respeite as decisões de produto.
- Trabalhe incrementalmente.
- Documente o que foi feito.
- Valide antes de avançar.

**A missão é construir uma ferramenta que funcione de verdade em uma sala de aula, com equipamentos convencionais, oferecendo ao professor uma experiência natural de interação com a lousa digital.**
