# Especificação: Darwin Goals Engine

## Visão Geral
O Darwin Goals Engine é um sistema de observabilidade e métricas inspirado no Google Analytics, permitindo que PMs definam objetivos para agentes de IA e meçam sua performance através de *Hard Rules* e *Semantic Evaluation*.

## Arquitetura de Métricas (Híbrida)

### 1. Hard Rules (Performance & Eficiência)
Validadores de regra determinísticos. Focados em métricas quantitativas extraídas diretamente da telemetria (OpenTelemetry).
- **Métricas Base:** `token_count`, `latency_ms`, `message_depth` (turnos).
- **Definição:** `{"metric": "tokens", "operator": "<", "value": 500}`.
- **Vantagem:** Baixo custo, alta precisão, execução imediata.

### 2. Semantic Evaluation (Qualidade & Intenção)
Realizado pelo *Referee Agent*. Focado em qualidade subjetiva e eficácia da tarefa.
- **Processo:** O Referee Agent analisa o log completo da conversa (Contexto + Metas) e atribui um *Score de Sucesso*.
- **Definição:** Prompt de critério de sucesso (ex: "O agente resolveu o ticket de suporte com tom empático?").
- **Vantagem:** Captura nuances que regras não conseguem medir.

## Componentes de Integração
- **Goal DSL:** Formato estruturado (JSON/YAML) para o PM definir o que é sucesso.
- **Event Registry:** Interface no SDK (`darwin-client-lib`) para disparar eventos customizados durante a execução do agente.
- **Referee Agent Engine:** Camada LLM que processa as conversas pendentes de avaliação após a finalização da sessão.

## Workflow de Otimização
1. **Definição:** PM define Goals via DSL.
2. **Coleta:** SDK envia telemetria + eventos para o Backend.
3. **Validação:** Backend aplica *Hard Rules* e escala o *Referee Agent* para *Semantic Evaluation*.
4. **Cálculo de Fitness:** O *GePa Engine* consolida os resultados em um Score Final para nortear mutações genéticas.
