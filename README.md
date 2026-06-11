# Darwin Loop

Darwin Loop is an autonomous optimization platform for AI Agents. It uses a reflective loop of telemetry, genetic mutation (GePa), and A/B testing to evolve agent prompts and weights, continuously improving performance based on custom Product Manager (PM) goals.

## The Reflective Optimization Loop

Darwin Loop operates on a closed-loop optimization cycle:

1.  **Telemetry Collection [IMPLEMENTED]:** The `darwin-client-lib` captures full interaction context, token usage, latency, and custom events.
2.  **Goal Evaluation [IN PROGRESS]:** The `Goal Engine` validates interactions against predefined performance KPIs (tokens, message count) and semantic quality goals.
3.  **Reflection & Analysis:** The system logs interactions and goal attainment scores for analysis.
4.  **Genetic Mutation (GePa):** (Planned) The GePa engine proposes mutations to prompts or weights based on performance.
5.  **A/B Testing & Deployment:** (Planned) Optimized versions are deployed and compared against the baseline.

## Architecture

- **`lib/`**: Contains the SDK (`darwin-client-lib`) for telemetry and the `Goal Engine` for KPI evaluation.
- **`backend/`**: FastAPI-based server for persistence and experiment management.
- **`tests/`**: Suite of unit and integration tests for core logic and goal validation.

## Status

- [x] SDK Implementation (Telemetry, Context Tracking, Privacy Scrubber)
- [x] Backend Infrastructure (FastAPI, SQLAlchemy)
- [x] Goal Engine Logic (Hard Rule Validation)
- [ ] Genetic Mutation Engine (GePa)
- [ ] PM Playground Dashboard
- [ ] Fine-tuning Pipeline Integration

## Getting Started

1. Install the SDK: `pip install darwin-client-lib`
2. Initialize with your agent: `darwin = DarwinClient(api_key="...")`
3. Track your goals: Define KPIs based on performance thresholds.

---
*Built for autonomous AI evolution.*
