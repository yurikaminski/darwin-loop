# DarwinLoop AI Usage Dashboard — design context

Input for the design loop. Facts here were verified against real Claude Code OTel payloads (CLI + desktop Code tab) on 2026-10-22.

## Goal

A complete view of the team's AI usage: adoption, prompt quality (what could improve), token/cost savings, value generated, tool/env health, governance.
**Aggregated view with drill-down to the individual** (team → squad → person → session → turn).

## Decided constraints

- Storage: BigQuery dataset `darwinloop_telemetry` in GCP project `brain003-mvp` (location `southamerica-east1`).
- Hosting: Cloud Run (one service: OTLP/HTTP JSON ingest + dashboard web app).
- Prompt/response text kept 30 days (partition expiration), then only derived fields survive (category, tone, friction flags, lengths).
- v1 has no LLM classifier yet (`lib/detection/classify_feedback` is a stub). Category/tone in v1 = keyword heuristics at ingest; an LLM judge is a later upgrade.
- No people→squad mapping exists in telemetry. A `people` table (email → name, squad, role, start date) is maintained manually or via `OTEL_RESOURCE_ATTRIBUTES=team=<squad>`.
- `cost_usd` is the client's estimate. On seat plans (Team/Max) it's notional, not billed — value framing must handle both.

## Signals available (OTLP)

Resource attrs: `service.name` (`claude-code` = CLI, `claude-code-desktop` = desktop Code tab), `service.version`, `os.type`, `host.arch`, custom `OTEL_RESOURCE_ATTRIBUTES` (e.g. `team`, `deployment.environment`).

Identity attrs on every event: `user.id` (hash), `user.email`, `user.account_uuid`, `organization.id`, `session.id`, `terminal.type`, `event.timestamp`, `event.sequence`. Turn key: `prompt.id`.

### Events (`POST /v1/logs`, body = event name)

| event | key attributes |
|---|---|
| `user_prompt` | `prompt_length`, `prompt` (text when `OTEL_LOG_USER_PROMPTS=1`) |
| `api_request` | `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `cost_usd`, `duration_ms`, `ttft_ms`, `query_source` (`sdk`/`main` = agent; `prompt_suggestion`, `generate_session_title`, `auxiliary` = overhead), `effort` |
| `api_error` | model, error, status (shape not yet observed) |
| `tool_decision` | `tool_name`, `decision` (accept/reject), `source` (`config` = rules/auto mode, `user_reject` = human denied), `tool_use_id` |
| `tool_result` | `tool_name`, `success`, `duration_ms`, `tool_input_size_bytes`, `tool_result_size_bytes` (no file path / command content) |
| `assistant_response` | `response_length`, `response` (text), `model`, `query_source` |
| `permission_mode_changed` | `from_mode`, `to_mode` (auto/default/...) |
| `mcp_server_connection` | `status`, `transport_type`, `duration_ms`, `error_code` |
| `hook_execution_*`, `plugin_loaded`, `managed_settings_resolved` | environment noise / config inventory |

A human-rejected tool has a `tool_decision` with no matching `tool_result`, and the turn ends with no `assistant_response`.

### Metrics (`POST /v1/metrics`)

`claude_code.session.count` (start_type fresh/resume), `active_time.total`, `cost.usage`, `token.usage` (type input/output/cacheRead/cacheCreation), `lines_of_code.count` (added/removed), `code_edit_tool.decision` (decision, source, tool_name, language). Documented but not yet observed: `commit.count`, `pull_request.count`. Project = `vcs.repository.name` (`OTEL_METRICS_INCLUDE_REPOSITORY=true`) else basename of `workspace.host_paths[0]` → `attrs.dl_project`. Skills/commands: `user_prompt.command_name/command_source`, Skill tool `tool_parameters.skill_name`, `api_request.skill.name` (names need `OTEL_LOG_TOOL_DETAILS=1` / Cowork `toolDetails`; detail payloads are scrubbed at ingest).

### Observations from tests

- Context baseline ~100k cache-read tokens per call even for trivial prompts (plugins/MCP/CLAUDE.md).
- First turn of a session (cold cache) cost ~$0.21 vs ~$0.01 for following calls.
- Auxiliary calls (`prompt_suggestion`) ≈ 5% of turn cost.
- A broken MCP server failed on every turn, one taking 8.9s.

### Not covered by this telemetry

Cowork, claude.ai chat, Office agents (separate telemetry, untested). Business outcomes (PR cycle time, incidents) need GitHub/Jira joins (out of v1, but the design should leave a slot).

## Visual identity (darwinloop.org)

- Dark: background `#0A0A0A`, text `#FAFAFA`.
- Primary `#8ED563` (lime), accent/link `#199953` (green), CTA `#23F884` (neon green, dark text).
- Fonts: Inter (body/headings), JetBrains Mono (numbers, code, labels).
- Square corners (radius 0; buttons 4px), no shadows, 4px base spacing, developer/terminal tone, numbered steps ("01 Intercept").
- Logo: https://darwinloop.org/assets/logo-BXXZ-iFy.png
- Product vocabulary: implicit feedback, re-prompts, corrections, abandonment, NFR/PFR/AINPS metrics, Intercept → Detect → Mutate → Validate loop.
