# Darwin Loop

Plataforma de otimização de agentes baseada em auto-evolução de prompts, fine-tuning via algoritmos genéticos (GePa) e observabilidade via OpenTelemetry. Focada em capacitar Product Managers (PMs) a escalar agentes de IA com qualidade e previsibilidade.

## Funcionalidades Principais
- **Otimização Reflexiva:** Ciclo contínuo de Feedback -> Mutação -> Teste A/B -> Deployment.
- **Darwin Goals Engine:** Sistema de KPIs para agentes (estilo Google Analytics), permitindo definir metas de performance e qualidade em linguagem natural.
- **Observabilidade:** Telemetria nativa com OpenTelemetry (OTel).
- **Privacidade:** PII Scrubbing automático para garantir compliance.

## Estrutura do Projeto
- `lib/`: SDK do cliente para coleta e gerenciamento de contexto.
- `backend/`: API (FastAPI) para processamento, armazenamento de versões e experimentos.
- `tests/`: Suíte de testes automatizados de core e metas.
- `docs/specs/`: Especificações técnicas dos módulos (ex: Goals Engine).
