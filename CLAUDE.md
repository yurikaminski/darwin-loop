# DarwinLoop

See README.md for the modules. The AI usage dashboard lives in `dashboard/`. Read `dashboard/README.md` before touching telemetry: it covers setup, the env vars, Cowork config and privacy.

## Dashboard rules

- Telemetry setup for every Claude Code user needs `OTEL_METRICS_INCLUDE_REPOSITORY=true` (projects) and `OTEL_LOG_TOOL_DETAILS=1` (skills and MCP names). Cowork needs an admin to configure it, with `toolDetails` in `otlpContentCapture`.
- `raw_events` never expires. Any attribute that can carry commands, paths, diffs or file contents must be dropped in `otlp._scrub_details`, with a test, before the flag that sends it is enabled.
- Prompt and response text only goes to `raw_texts` (30-day expiry).
- Metrics are defined once, in `dashboard/views.sql`. Cards read them through `dashboard/queries.py`. Deploy with `bash dashboard/deploy.sh`, which applies the views first.
- GCP project `brain003-mvp`: touch only the `darwinloop_telemetry` dataset and the `darwinloop-dash` service. Never commit secrets (`dl-dash-pass`, `dl-ingest-token`) or OTLP dumps, because they contain PII.
