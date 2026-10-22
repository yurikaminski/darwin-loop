# DarwinLoop AI usage dashboard

OTLP/HTTP JSON ingest → BigQuery (`brain003-mvp.darwinloop_telemetry`) → read-only dashboard on Cloud Run (`darwinloop-dash`, southamerica-east1).

- `main.py`: ingest (`/v1/logs`, `/v1/metrics`, Bearer token) and dashboard API (`/api/{name}`, login).
- `otlp.py`: OTLP → rows. Prompt text goes to `raw_texts` (30-day expiry) and never to `raw_events`. Tool details are scrubbed here (see Privacy).
- `views.sql`: every metric (v_events → v_calls / v_turns → v_cost_alloc / v_sessions / v_person_day).
- `queries.py`: one named query per dashboard card.
- `deploy.sh`: applies `views.sql`, then deploys. Tests: `python -m pytest -q`.

## Setup: Claude Code (each person)

Add this to `~/.claude/settings.json` → `env`. Managed settings work too, for org rollout.

| Variable | Value | What it unlocks |
|---|---|---|
| `CLAUDE_CODE_ENABLE_TELEMETRY` | `1` | everything |
| `OTEL_LOGS_EXPORTER` / `OTEL_METRICS_EXPORTER` | `otlp` | events / counters |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/json` | the format the ingest parses |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Cloud Run URL | |
| `OTEL_EXPORTER_OTLP_HEADERS` | `Authorization=Bearer <ingest token>` | the secret `dl-ingest-token`; never commit it |
| `OTEL_RESOURCE_ATTRIBUTES` | `team=<squad>,deployment.environment=<env>` | squad when the person is not in `people` |
| `OTEL_METRICS_INCLUDE_REPOSITORY` | `true` | **Projects**: `vcs.repository.name` on every event (Claude Code ≥ 2.1.269) |
| `OTEL_LOG_TOOL_DETAILS` | `1` | **Skills & MCP**: real skill, MCP server and tool names |
| `OTEL_LOG_USER_PROMPTS` | `1` (opt-in) | intent, domain and text correction cues; without it those show as "no text" |

Built-in and custom slash commands (`command_name`, `command_source`) arrive on every `user_prompt` without extra flags. Custom command names need `OTEL_LOG_TOOL_DETAILS=1`, otherwise they arrive as `custom`.

## Setup: Cowork (org admin)

Go to claude.ai → Admin settings → Cowork → OpenTelemetry, and set the same endpoint, headers and protocol (`service.name` arrives as `cowork`).

- **Projects:** Cowork has no project concept. The ingest uses the name of the first connected folder (`workspace.host_paths`), which is always sent.
- **Skill names:** add `toolDetails` to `otlpContentCapture`, otherwise the Skill tool shows as "(name not exported)".
- **Prompt text:** add `prompts` to `otlpContentCapture`. This is the same opt-in as above.

## How project is derived

The project is `vcs.repository.name`. If that is missing, it falls back to the folder name of `workspace.host_paths[0]`. If both are missing, the session counts as "outside a project".

It is stored as `attrs.dl_project`. Sessions from before the setup show as outside.

## Privacy (what the ingest keeps)

With tool details on, Claude Code and Cowork send shell commands, file paths, diffs and tool inputs. `otlp._scrub_details` drops all of them before insert and keeps only these names:

- `skill_name`
- `mcp_server_name`
- `mcp_tool_name`

Full `workspace.host_paths` are dropped too; only the folder name survives as the project. Rows in `raw_events` don't expire, so anything new that might carry content must be scrubbed in `otlp.py` (and tested in `test_otlp.py`) before it is turned on.

Sources:
- https://code.claude.com/docs/en/monitoring-usage
- https://support.claude.com/en/articles/14477985-monitor-cowork-activity-with-opentelemetry
