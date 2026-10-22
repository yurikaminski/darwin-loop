# DarwinLoop AI Usage Dashboard — Spec v2

Status: draft v2 (design loop iteration 2). Source of truth for signals: `docs/dashboard/context.md`.
Scope: Claude Code CLI (`service.name=claude-code`) and desktop Code tab (`claude-code-desktop`) only. Cowork, claude.ai chat and Office agents are out of scope.

Rule used throughout: if a number cannot be computed from the OTLP signals in context.md plus the `people`, `config`, `model_tiers`, `heuristic_labels` and `survey_responses` tables, it is marked **needs: <source>** and rendered as an empty slot. It is never estimated.

### Changes from v1

| Area | v1 problem | v2 fix |
|---|---|---|
| MCP | Assumed per-server connection stats. `mcp_server_connection` has no server name | Per-server health comes only from `tool_result` rows with `tool_name` `mcp__<server>__*`. Connection failures are an **unattributed** total. R2 split into R2a/R2b (§3 6.2, §6) |
| Hosting | IAP on one service would block OTLP clients | Two Cloud Run services from one image: `ingest` (public, bearer token checked in app) and `dashboard` (IAP) (§4.5) |
| Metrics | Stateless cumulative→delta conversion | Clients must send delta temporality. Cumulative points are rejected and counted. `api_request.cost_usd`/tokens is the **only** cost source (§4.1, §4.5) |
| Heuristics | Bare `não`/`no`/`ainda` and substrings (`ci`, `cri`, `spec`, `add`, `doc`) misfire | Word-boundary regex, correction cues only in the first 5 tokens, bare negation only when followed by punctuation. Validation gate: rates are labelled `beta` until ≥ 50 hand-labelled turns give precision ≥ 0.8 (§4.3) |
| Waste | Segments overlapped | One exclusive per-call allocation: overhead → cold-start excess → cost in friction turns → useful (§3 1.8) |
| Seats | No seat count | `config.seats_purchased`, exact 1.7 formula, unused-seat tile 1.12 (§3, §5) |
| LGPD | `raw_text` had no person key | `raw_text.user_id/user_email`, a deletion procedure that accounts for the streaming buffer and time travel, and a rule for `access_log` (§8) |
| Value | Savings and prompt improvement were only implied | Exec tile 1.11 "verified savings from actions" and per-person weekly trend 3.7 (§3, §5) |
| R3 | Undefined price of the cheaper model | `model_tiers` table. R3 is suppressed when the cheaper tier has no observed or configured price (§4.1, §6) |
| k-anon | 3 vs 5 | `config.k_anon_min` applies to every squad aggregate an exec or cross-squad viewer sees (§8.2) |
| Adopted nice-to-haves | — | Banded manager view, the scope trim, adoption depth (1.4b, 1.4c), definitions drawer, survey slot 1.13, "cost in friction turns (≤)" wording |

---

## 1. Personas and the questions they answer

| Persona | Primary page | Questions (each maps to a widget) |
|---|---|---|
| **Exec / AI value owner** (owns adoption and AI value metrics) | 01 Overview, 07 Insights | Is AI adopted, and is it growing (1.1, 1.2)? Is use deep or shallow: tools, MCP, auto mode, time-to-first-use for new joiners (1.4, 1.4b, 1.4c)? Which squads lag (1.3)? What does a user cost, and is the seat plan worth it compared with API pricing (1.6, 1.7)? How many seats are unused, and how much money is that (1.12)? Where is spend wasted (1.8)? Which 3 actions matter this month (1.9)? What did the actions we already took save (1.11)? What outcome evidence exists (1.10 GitHub/Jira, 1.13 survey)? |
| **Eng manager / tech lead** | 02 Squad, 06 Health, 07 Insights | Who on my squad has not started, or is struggling, and needs coaching (2.2)? Which kinds of work fail most, so I can add a CLAUDE.md rule or a skill (2.3, R5)? Why do turns fail (2.4)? Which tools and MCP servers break (6.1, 6.2)? Are people approving everything, or rejecting a lot (6.4)? Is the squad improving (2.6)? |
| **Individual dev** | 03 Person (self), 04 Session, 05 Turn | Where do my turns go wrong (3.3, 3.5)? Are my prompts too short for the kind of task (3.3)? Am I paying a cold-start tax (3.4)? Am I improving week over week (3.7)? What does my manager see about me (3.8)? |

Personas map to `people.role`: `exec`, `manager`, `dev`, `admin`. Access rules are in §8.

---

## 2. Navigation and drill-down model

```
Org (01 Overview) ──> Squad (02) ──> Person (03) ──> Session (04) ──> Turn (05)
       │                  │               │
       └── 06 Health ─────┴── 07 Insights ┘   (both filterable to squad/person; every row links into the hierarchy)
```

**Global filter bar** (sticky on every page; state lives in the URL query string, so every view is a shareable link):

| Filter | Values | Source field |
|---|---|---|
| `from`, `to` | date range, default last 28 days, presets 7/28/90d | `event_ts` (stored UTC, displayed America/Sao_Paulo) |
| `month` | calendar month, used only by the monthly money widgets 1.7, 1.12. Default: last complete month. The current month is allowed and labelled `MTD` | `event_ts` in America/Sao_Paulo |
| `squad` | multi-select from `v_person.squad`, including an `unassigned` bucket | `people.squad`, fallback resource attr `team` |
| `surface` | `cli`, `desktop`, all | `service.name` |
| `model` | multi-select of observed models | `api_request.model` |

URL scheme: `/?from=&to=&month=&squad=&surface=&model=`, `/squad/<squad>`, `/person/<user_id>`, `/session/<session_id>`, `/turn/<prompt_id>`. People are addressed by the `user.id` hash in URLs and exports, never by email.

**Drill rules (every aggregate links down):**

- A KPI tile opens the chart that breaks it down on the same page, or the next level filtered to the tile's scope.
- A chart bar or point keyed by squad goes to `/squad/<squad>` with the same filters. Keyed by person, it goes to `/person/<id>`. Keyed by day or week, it reloads the same page with `from`/`to` set to that period.
- Table rows: squad → 02, person → 03, session → 04, turn → 05, tool or MCP server → 06 filtered to it, insight → its evidence list (sessions and turns).
- The breadcrumb always shows `Org / <squad> / <person> / <session> / <turn>` and carries the filters along.
- When the viewer lacks the role for the target level, the drill is blocked and shows a lock icon with the reason (§8). When a squad has been merged into "other" for k-anonymity, its bar does not link down for exec or cross-squad viewers.
- **Definitions drawer:** every KPI tile and chart header has a `def` button. It opens a side drawer with the exact SQL that produced the number (returned by the API, not written separately), `n`, `heuristic_version`, the beta/validated status of the heuristic (§4.3), and data freshness (`MAX(ingest_ts)`). Each `/api/<widget>` response is `{rows, sql, params, n, heuristic_version, heuristic_status, generated_at}`, so the drawer cannot drift from the number.

---

## 3. Pages and widgets

Notation:
- `T`: turns in filter scope (from `v_turns`). `S`: sessions. `P`: people in `v_person` with `active = true`.
- `A`: agent API calls (`query_source IN ('sdk','main')`). `X`: overhead API calls (any other `query_source`).
- Rates always show `n` beside them.

**Low-data rule (global):** a rate whose denominator is under `config.min_turns_rate` (20) turns, or under 3 people, renders grey as "n=<k>, low data". It is left out of rankings, bands and insights.

**Beta rule (global):** every number that uses `correction_kw`/`next_correction_kw` or `category` carries a `beta` chip until the heuristic passes the validation gate in §4.3. This covers 1.5, 2.1 clean, 2.2 correction band, 2.3, 2.4 correction segment, 3.1 clean, 3.3, 3.7, and the friction segment of 1.8. The chip tooltip reads: "keyword heuristic not yet validated (n labelled = k, precision = p)". Clean-turn tiles also show a secondary "behavioural only" number: the same rate with `next_correction_kw` removed from `is_friction`. That number never needs the beta label.

### 01 Overview (exec)

| # | Widget | Question | Chart | Metric definition | Drill | Empty / low data |
|---|---|---|---|---|---|---|
| 1.1 | Weekly active users | Is it adopted? | KPI tile + 12-week sparkline | `WAU = COUNT(DISTINCT user_id)` with ≥ 1 turn in the ISO week. The tile shows the last full week and the delta vs the prior week | 1.3 | "No telemetry received yet" + link to the setup doc (§4.5) |
| 1.2 | Penetration | What share of the team uses it? | KPI tile (%) | `WAU / COUNT(people WHERE active AND start_date <= week_end)` | 1.3 | **needs: people table** when `people` is empty |
| 1.3 | Adoption by squad | Which squads lag? | Horizontal bar per squad. Value = penetration; label = WAU/headcount | 1.2 grouped by squad. Squads with active headcount < `k_anon_min` are merged into "other (< k)" (§8.2); if "other" is itself < k it is suppressed | `/squad/<s>` (not for merged rows) | A squad with 0 WAU shows an empty bar, not a hidden one |
| 1.4 | Depth of use | Habitual or occasional? | Histogram: people by active days in the 28 days ending `to` (buckets 1, 2–5, 6–12, 13+) | `active_days = COUNT(DISTINCT DATE(start_ts))` per person | bucket → 02 people list filtered to the bucket (role-gated) | — |
| 1.4b | Feature reach | Are people using the agent's depth, or only chat? | 3 small bars, % of active people (≥ 1 turn in range) | `uses_mcp` = ≥ 1 `tool_result` with `tool_name LIKE 'mcp\_\_%'`; `uses_auto` = ≥ 1 `permission_mode_changed` with `to_mode='auto'`; `uses_resume` = ≥ 1 `claude_code.session.count` point with `start_type='resume'`. Each one: `COUNT(DISTINCT people with flag) / COUNT(DISTINCT active people)` | bar → 02 table filtered to people without the flag | < 3 active people: low data |
| 1.4c | Time to first use | How fast do new joiners start? | KPI (median days) + table of joiners from the last 180 days (managers and admins only; execs see the median and count) | per person with `start_date` in the last 180 days: `days_to_first = DATE_DIFF(DATE(MIN(turn.start_ts)), start_date, DAY)`; NULL = not yet activated. KPI = median over activated joiners, plus the count still NULL | row → `/person/<id>` | **needs: people.start_date**; "no joiners in 180 days" |
| 1.5 | Clean-turn rate `beta` | Does the AI do what people asked? | KPI tile + weekly line; secondary "behavioural only" number | `1 − friction_rate`; `friction_rate = COUNTIF(is_friction) / COUNT(T)` (§4.2) | 02 friction by squad (2.3) | low-data rule |
| 1.6 | Notional cost per active person | What does one user cost? | KPI tile (USD/week) | `SUM(cost_usd over A∪X in the last full ISO week) / WAU`. Subtitle: "notional on seat plans; seat = $<seat_usd_month>/month" | 1.8 | — |
| 1.7 | Seat leverage | Is the seat plan worth it vs API pricing? | Bullet chart: org row + one row per squad; marker = leverage, reference line at 1.0 | For month `m`: `active_people_m = COUNT(DISTINCT user_id with ≥ 1 turn in m)`; `leverage = SUM(cost_usd of A∪X in m) / active_people_m / config.seat_usd_month`. > 1 means API pricing would cost more than the seat; < 0.3 means the seat is lightly used. Squads with active_people_m < k_anon_min are merged into "other" | 02 (managers: person rows show a leverage band, not a value) | Hidden when `plan_type='api'`; then the tile shows real monthly spend instead |
| 1.8 | Where spend goes | Where is spend wasted? | One 100% stacked bar + USD per segment: overhead, cold-start excess, **cost in friction turns (≤)**, useful | Exclusive allocation per API call (§4.2 `v_cost_alloc`): (1) `X` call → overhead; (2) `A` call with `call_rank=1` → `cold_excess = GREATEST(cost − ref_median_cost(model), 0)`; (3) remainder of `A` calls in turns with `is_friction` → friction; (4) everything else → useful. Segment = `SUM` of its column; the 4 sum exactly to total cost. `ref_median_cost(model)` = median `cost_usd` of `A` calls with `call_rank > 1` for that model in the date range | segment → 07 filtered to the matching rules (overhead → R8, cold → R7, friction → R5/R4) | < 20 agent calls: low data |
| 1.9 | Top 3 actions | What do I do this month? | Ranked list (top 3 open insights by impact from `v_insights`, org/squad scope only) | §6 | insight evidence | "No actionable patterns yet (needs ≥ 14 days of data)" |
| 1.10 | Outcomes | Did delivery improve? | Slot card | **needs: GitHub** (PR cycle time, PRs/active dev), **needs: Jira** (lead time). `pull_request.count` and `commit.count` metrics are shown if ever received (documented, not yet observed) | — | Empty slot with a "connect GitHub" CTA |
| 1.11 | Verified savings from actions | What did the actions we took save? | KPI tile with 3 lines: USD/month (≤, notional on seat plans), friction turns/month, tool wait hours/month; plus "k of n done actions measured" | Sum over insights with `status='done'` and `done_at ≤ today − 14d` of the 7.2 delta for that insight (definition in 7.2), normalised to 30 days. Negative deltas are included (net figure). Insights with fewer than 14 days since `done_at` count as "pending" | → 7.2 | "No actions marked done yet" |
| 1.12 | Unused seats | How much seat money can be reclaimed? | KPI tile: count + USD/month | `unused = GREATEST(config.seats_purchased − active_people_m, 0)`; `reclaimable_usd = unused × seat_usd_month` | 02 people tables with status `not activated` / `has seat, inactive` (managers) | **needs: config.seats_purchased**; hidden when `plan_type='api'` |
| 1.13 | Self-reported time saved | The only route to an hours figure | Slot card: median minutes saved per week per respondent, by category, monthly; "self-reported, n=k" | `survey_responses` (§4.1). Aggregated only, `n ≥ k_anon_min` per cell | — | **needs: survey** (monthly Google Form → CSV load) |

Cut as vanity: total prompts, total tokens, and total lines of code as headline numbers. They appear only as context on drill pages.

### 02 Squad (manager)

| # | Widget | Question | Chart | Metric definition | Drill | Empty / low data |
|---|---|---|---|---|---|---|
| 2.1 | Squad KPI row | Health at a glance | 4 tiles: WAU/headcount, clean-turn rate `beta`, notional cost/active person/week, edit acceptance | Edit acceptance = `SUM(value of code_edit_tool.decision WHERE decision='accept') / SUM(value of code_edit_tool.decision)` (delta points only, §4.5) | tile → 2.2 sorted by that column | low-data rule |
| 2.2 | People table | Who needs help? | Table, one row per person in the squad (including people who never used it) | Columns, by name: name, last active date, active days (28d), turns, uses MCP / auto (1.4b flags), status badge. **Banded columns** (shown as `low` / `typical` / `high` vs the squad, never as exact numbers): notional cost/week, correction rate `beta`, reject rate, clean-turn rate. Band = below the squad P25 / P25–P75 / above P75, computed only when the person has n ≥ 20 turns and the squad has ≥ 3 people with n ≥ 20; otherwise "—". Status: `not activated` = 0 turns and `start_date + 14d < today`; `struggling` = friction_rate ≥ squad median + 15pp with n ≥ 20; `power` = active days ≥ 13; `has seat, inactive` = `people.has_seat` and 0 turns in month `m` (only if the column is filled). Sort: status (not activated, struggling, rest), then name. Never sorted by volume | row → `/person/<id>` | People with no activity are listed with "0", not hidden; the adoption gap is the point |
| 2.3 | Friction by category `beta` | Which kinds of work fail? | Horizontal bar per category: friction rate; bar label n | `friction_rate` grouped by `v_turns.category` | bar → turn list filtered to that category with `is_friction` (derived fields only for managers) | category with n < 20 greyed |
| 2.4 | Friction mix | Why do turns fail? | Stacked weekly bars: user_reject / tool failure / fast re-prompt / correction `beta` / abandoned | Counts of each flag over T. A turn can carry several flags, so the stack shows flag counts and the axis says "flags", not "turns" | segment → turn list | — |
| 2.6 | Squad trend | Getting better? | Lines over 12 weeks: weekly clean-turn rate (and its behavioural-only line) and WAU | per ISO week | point → same page, that week | < 3 weeks: table instead of line |

Deferred to v1.1: 2.5 model × category heatmap.

### 03 Person (self, or the person's manager)

| # | Widget | Question | Chart | Metric definition | Drill | Empty |
|---|---|---|---|---|---|---|
| 3.1 | Person KPI row | How am I doing vs my squad? | 5 tiles, each with the squad median as a tick: active days, clean-turn rate `beta`, turns/session, median prompt length, notional cost/week. For the manager viewer, the clean rate and cost tiles show the band (as in 2.2), not the value | from `v_person_day` | — | < 5 turns: "Not enough activity yet" |
| 3.2 | Activity calendar | When do I use it? | 28-day calendar heatmap, value = turns/day | `COUNT(T)` per day | day → 3.5 filtered to that day | — |
| 3.3 | Prompt length vs friction `beta` | Do short prompts hurt me? | Bars: friction rate by prompt length bucket (`<80`, `80–300`, `300–1000`, `>1000` chars), person vs squad | `friction_rate` grouped by `length_bucket` | bucket → turn list | bucket n < 10 greyed |
| 3.4 | Cold-start tax | Am I opening too many short sessions? | KPI only (scatter deferred to v1.1) | `cold_share = SUM(cold_excess) / SUM(cost A)` from `v_cost_alloc`; plus `short_session_share = COUNT(sessions with n_turns ≤ 2) / COUNT(S)` | → 3.5 sorted by turns ascending | — |
| 3.5 | Sessions table | Which sessions went well or badly? | Table | start, surface, duration (`active_s` if present, else last − first event), turns, friction turns, notional cost, lines +/−, start_type (fresh/resume), main model | row → `/session/<id>` | — |
| 3.6 | Tool profile | Which tools do I depend on, and which do I reject? | Table per tool_name | calls, failure rate, user rejects, p95 duration | row → 06 filtered to that tool and person | — |
| 3.7 | Weekly trend `beta` | Am I improving? | Two small-multiple line charts over 12 ISO weeks: (a) clean-turn rate, person solid vs squad median dashed; (b) median `prompt_length` per week for the person's top 3 categories by turn count | (a) `1 − COUNTIF(is_friction)/COUNT(*)` per week; (b) `APPROX_QUANTILES(prompt_length, 2)[OFFSET(1)]` per week × category. Weeks with < 5 turns are drawn as gaps | point → 3.5 filtered to that week | < 3 weeks of data: "Trend appears after 3 active weeks" |
| 3.8 | What my manager sees | Transparency | The person's own 2.2 row, rendered exactly as the manager sees it (bands and badges), plus a "viewed by" list from `access_log` | same query as 2.2, filtered to self | — | — |

### 04 Session

| # | Widget | Question | Chart | Metric definition | Drill | Empty |
|---|---|---|---|---|---|---|
| 4.1 | Session header | What happened? | Text row | person, surface, version, os, start/end, start_type, permission modes seen (`permission_mode_changed`), total notional cost, cache hit ratio | — | — |
| 4.2 | Turn timeline | Where did it go wrong? | Horizontal timeline, one block per turn, width = duration, colour clean (`--primary`) / friction (`--bad`) / abandoned (`--muted`); gaps between turns labelled in seconds (fast re-prompts show as < 60 s gaps) | `v_turns` ordered by `start_ts` | block → `/turn/<prompt_id>` | — |
| 4.3 | Cost per turn | Was the first turn the expensive one? | Bar per turn, stacked: cold-start excess / other agent / overhead | `v_cost_alloc` summed per turn | bar → turn | — |
| 4.4 | Context size per call | Is context bloated? | Line: `cache_read_tokens + input_tokens + cache_creation_tokens` per A call, with a 100k reference line | raw per `api_request` | — | — |
| 4.5 | Outcome strip | What did it produce? | Text: lines added/removed, edit accept/reject counts | `lines_of_code.count`, `code_edit_tool.decision` for the session | — | "no edits" |

### 05 Turn

| # | Widget | Question | Chart | Metric definition |
|---|---|---|---|---|
| 5.1 | Prompt | What was asked? | Text block + labels (category, tone, length, heuristic_version, `beta` if applicable) | text from `raw_text` (only if ≤ 30 days old and the viewer is allowed, §8). Otherwise "text expired, derived fields only" or "text not captured" |
| 5.2 | Event waterfall | What did the agent do? | Rows ordered by `event.sequence`: api_request (model, tokens, cost, ttft, query_source), tool_decision (accept/reject + source), tool_result (tool, success, duration, sizes), assistant_response (length) | all events with this `prompt.id` |
| 5.3 | Friction flags | Why is it flagged? | Chips: `user_reject`, `tool_fail`, `fast_reprompt (<Ns)`, `correction_next` `beta`, `abandoned` | flags from `v_turns`, each linked to the event that set it |
| 5.4 | Response | What did it answer? | Collapsed text block | `raw_text` kind `response`, same access rules as 5.1 |
| 5.5 | Next turn | How did the user react? | Link card to the next turn with gap seconds and its tone label | `LEAD()` over the session |

### 06 Health & Governance (manager, admin; exec sees org and k-anon squad aggregates)

v1 ships 6.1, 6.2, 6.3, 6.4, 6.6, 6.8. Deferred to v1.1: 6.5 client versions, 6.7 plugin inventory (raw `plugin_loaded` / `managed_settings_resolved` rows are still stored).

| # | Widget | Question | Chart | Metric definition | Drill | Empty |
|---|---|---|---|---|---|---|
| 6.1 | Tool reliability | Which tools break? | Table: tool_name, calls, failure rate, p50/p95 duration, mean result size, time in failed calls | `tool_result` grouped by `tool_name`; `failure_rate = COUNTIF(success=false)/COUNT(*)`; `fail_time_s = SUM(duration_ms WHERE success=false)/1000` | row → turns with that tool failing | — |
| 6.2a | MCP servers (attributed from tool calls) | Which MCP servers' tools fail or are slow? | Table: server, tools seen, calls, failure rate, p95 duration, time in failed calls, people affected | from `tool_result` only: `mcp_server = REGEXP_EXTRACT(tool_name, r'^mcp__(.+?)__')`, rows where it is not NULL, grouped by server | row → sessions with failing calls to that server | "no MCP tool calls observed" |
| 6.2b | MCP connections (unattributed) | Are MCP connections failing, and how much time do they cost? | KPI row (attempts, failure rate, time lost) + bar by `error_code` + bar by `transport_type` + people affected (managers: by name; exec: count) | `mcp_server_connection` events: `attempts = COUNT(*)`; `failed = COUNTIF(status != 'connected')`; `time_lost_s = SUM(duration_ms WHERE status != 'connected')/1000`. **Per-server attribution: needs: server name attr (verify payload).** During build, check `attrs` JSON on real `mcp_server_connection` rows for any server-name key; if one exists, add it to `v_mcp_conn` and merge 6.2a/6.2b | row → sessions with failed connects | "no MCP connections observed" |
| 6.3 | API latency and errors | Is the model side slow? | Lines: p50/p95 `ttft_ms` and `duration_ms` per day per model; bar of `api_error` count per day; list of unknown `query_source` values seen | `api_request`, `api_error`. Error breakdown by status: **needs: observed api_error shape** (v1 shows the count only) | day → sessions | — |
| 6.4 | Permission posture | Are people auto-approving everything? | Stacked bar per squad (k-anon): share of `tool_decision` by source (`config` / user accept / `user_reject`); plus the share of people who switched to auto mode | `COUNT(tool_decision) by source / total`; merge rule §8.2 | squad → 02 | — |
| 6.6 | Context baseline | How heavy is our default context? | KPI + bar per squad (k-anon): median `cache_read_tokens` of the first A call of each turn | `APPROX_QUANTILES(cache_read_tokens, 2)[OFFSET(1)]` over A calls that are first in their turn | squad → 02 | — |
| 6.8 | Ingest health (admin) | Is the data complete? | Table: rejected cumulative metric points by person/service, last event per person, rows from emails missing in `people` | `ingest_rejects`, `MAX(event_ts)` per user | row → setup doc | "all clients healthy" |

### 07 Insights

| # | Widget | Question | Chart | Metric definition | Drill |
|---|---|---|---|---|---|
| 7.1 | Action list | What should we do? | Card list sorted by impact; each card = rule, scope (org/squad/person), evidence numbers, recommended action, estimated impact, `beta` chip if the rule uses keyword heuristics, status (open/done/dismissed in `insight_status`) | rows of `v_insights` (§6) | card → evidence turns/sessions |
| 7.2 | Done tracker | Did the action work? | Before/after mini chart per insight marked done; delta row feeding 1.11 | For insight `i` with trigger metric `M_i` over scope `s_i`: `before` = `M_i` over the 14 days before `done_at`; `after` = `M_i` over the days from `done_at` to `min(done_at+28d, today)` (needs ≥ 14). Delta per 30 days: USD rules (R1, R3, R7, R8): `(cost_per_turn_before − cost_per_turn_after) × turns_after_per_30d` of the affected component; turn rules (R4, R5, R6, R12): `(rate_before − rate_after) × turns_after_per_30d`; time rules (R2a, R2b, R11): `(fail_time_per_turn_before − after) × turns_after_per_30d`. Label: "before/after, not causal — no control group" | → evidence |

---

## 4. Derived data model (BigQuery `brain003-mvp.darwinloop_telemetry`, `southamerica-east1`)

Dataset options: `max_time_travel_hours = 48` (minimum, limits how long deleted data stays recoverable; §8).

### 4.1 Tables

| Table | Grain | Key columns | Partition / retention |
|---|---|---|---|
| `raw_events` | one OTLP log record | `event_ts TIMESTAMP`, `ingest_ts`, `event_name`, `session_id`, `prompt_id`, `event_sequence INT64`, `user_id`, `user_email`, `account_uuid`, `org_id`, `service_name`, `service_version`, `os_type`, `host_arch`, `terminal_type`, `team_attr` (resource `team`), `env_attr`, `attrs JSON` (all event attributes **minus** `prompt` and `response`), `derived JSON` (`category`, `tone`, `correction_kw`, `length_bucket`, `heuristic_version`; `user_prompt` only) | `PARTITION BY DATE(event_ts)`, `CLUSTER BY user_email, session_id`, expiration 400 days |
| `raw_text` | one prompt or response text | `event_ts`, `session_id`, `prompt_id`, `event_sequence`, **`user_id`, `user_email`**, `kind` (`prompt`/`response`), `text STRING` | `PARTITION BY DATE(event_ts)`, `CLUSTER BY user_email`, **expiration 30 days** |
| `raw_metrics` | one OTLP **delta** data point | `ts`, `start_ts`, `metric_name`, `value FLOAT64`, `user_id`, `user_email`, `session_id`, `service_name`, `attrs JSON` (type, decision, source, tool_name, language, start_type) | `PARTITION BY DATE(ts)`, `CLUSTER BY user_email`, 400 days. Only delta sums and gauges are stored (§4.5) |
| `ingest_rejects` | one rejected batch slice | `ts`, `reason` (`cumulative_temporality`, `bad_token`, `org_mismatch`, `deleted_subject`), `metric_name`, `user_id`, `service_name`, `service_version`, `points INT64` | 90 days. No email column |
| `people` | one person | `email`, `user_id_hash`, `name`, `squad`, `role` (`exec`/`manager`/`dev`/`admin`), `manager_email`, `squad_lead BOOL`, `start_date`, `active BOOL`, `has_seat BOOL` (optional) | none; CSV load |
| `config` | single row | `plan_type` (`seat`/`api`), `seat_usd_month`, **`seats_purchased INT64`**, `org_id`, `fast_reprompt_s` (60), `min_turns_rate` (20), `k_anon_min` (5), **`kw_validated BOOL`**, **`kw_label_n`**, **`kw_precision_correction`**, **`kw_validated_at`**, `kw_validated_by` | none |
| `model_tiers` | one model pattern | `model_pattern` (LIKE pattern, e.g. `claude-opus-%`), `tier` (`large`/`medium`/`small`), `list_usd_per_mtok_input`, `_output`, `_cache_read`, `_cache_write`, `updated_at` | none; edited by admin from the published price list |
| `heuristic_labels` | one hand-labelled turn | `prompt_id`, `heuristic_version`, `true_is_correction BOOL`, `true_category`, `labeller_email`, `labelled_at` | none. Derived labels only, no text |
| `insight_status` | one insight | `insight_key`, `status`, `owner_email`, `done_at`, `note` | none |
| `access_log` | one page view of a person/session/turn | `viewer_email`, `target_user_id`, `level`, `ts`, `reason` | 400 days |
| `deleted_subjects` | one erased person | `user_id`, `email_sha256`, `requested_at`, `completed_at` | none; the ingest drops new records from these identities |
| `survey_responses` (slot) | person × month × category | `email`, `month`, `category`, `minutes_saved_week` | 400 days. **needs: survey** |
| `outcomes_*` (slot) | per PR / issue | **needs: GitHub** (`outcomes_github_pr`: author_email, opened_at, merged_at, additions, deletions), **needs: Jira** (`outcomes_jira_issue`) | out of v1; views `LEFT JOIN` them when present |

Text lives in its own table because partition expiration deletes whole partitions. That lets the 30-day rule apply to text while events survive. Category and tone are computed at ingest so they outlive the text.

**Single cost source:** `api_request.cost_usd` and its token fields are the only source for every cost and token widget. `claude_code.cost.usage` and `claude_code.token.usage` are stored in `raw_metrics` but no view or widget reads them. This prevents double counting. Metrics feed only `session.count` (start_type), `active_time.total`, `lines_of_code.count` and `code_edit_tool.decision`.

### 4.2 Derived views

All views are plain views in v1, and every one filters out `user_id IN (SELECT user_id FROM deleted_subjects)`. shortcut: plain views re-scan raw tables on every load; upgrade to scheduled `MERGE` into tables when `raw_events` passes ~10 GB or page load exceeds 3 s.

**`v_person`**: `people` FULL JOIN identities seen in `raw_events` on email. `squad = COALESCE(people.squad, team_attr, 'unassigned')`. Emails seen in telemetry but missing from `people` appear with squad `unassigned` and role `dev`, and are listed on 6.8.

**`v_api_calls`**: `raw_events WHERE event_name='api_request'`, unpacking `model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, cost_usd, duration_ms, ttft_ms, query_source, effort`. Adds `is_agent = query_source IN ('sdk','main')`, `call_rank = ROW_NUMBER() OVER (PARTITION BY session_id, is_agent ORDER BY event_ts, event_sequence)` (used only where `is_agent`), `turn_call_rank` (same, partitioned by `prompt_id`), and `tier` via `model_tiers` (`model LIKE model_pattern`).

**`v_turns`** (grain: `prompt_id`)

| Column | Definition |
|---|---|
| `start_ts` | `event_ts` of `user_prompt` |
| `end_ts` | `MAX(event_ts)` over all events with this `prompt_id` |
| `prompt_length`, `category`, `tone`, `correction_kw`, `length_bucket`, `heuristic_version` | from `user_prompt` attrs/derived |
| `n_agent_calls`, `agent_cost`, `overhead_cost`, tokens by type | from `v_api_calls`, split by `is_agent` |
| `main_model` | model with the largest agent cost in the turn |
| `n_tool_calls`, `n_tool_fail`, `fail_time_ms` | `tool_result` count, `COUNTIF(success=false)`, `SUM(duration_ms WHERE success=false)` |
| `n_user_reject` | `tool_decision WHERE source='user_reject'` (or `decision='reject' AND source != 'config'`) |
| `has_response` | any `assistant_response` with `query_source IN ('sdk','main')` or no query_source |
| `next_gap_s` | `TIMESTAMP_DIFF(LEAD(start_ts) OVER (PARTITION BY session_id ORDER BY start_ts), end_ts, SECOND)` |
| `next_correction_kw` | `LEAD(correction_kw)` over the same window |
| `is_fast_reprompt` | `next_gap_s IS NOT NULL AND next_gap_s < config.fast_reprompt_s` |
| `is_abandoned` | `NOT has_response AND next_gap_s IS NULL` (the last turn of the session ended without an answer) |
| `is_friction_behavioural` | `n_user_reject > 0 OR n_tool_fail > 0 OR is_fast_reprompt OR is_abandoned` |
| `is_friction` | `is_friction_behavioural OR next_correction_kw` |

Friction rate (canonical): `COUNTIF(is_friction) / COUNT(*)` over `v_turns`. Correction rate: `COUNTIF(next_correction_kw) / COUNT(*)`. Reject rate: `COUNTIF(n_user_reject > 0) / COUNT(*)`.

v1 tuning note: `n_tool_fail > 0` will over-flag, because the agent often recovers from a failed grep. The labelling sample (§4.3) also records `true_is_friction`. If tool-fail-only turns are judged clean in more than half the labelled cases, the condition changes to "a failure with no later success of the same tool in the turn" (`heuristic_version` bump).

**`v_cost_alloc`** (grain: one `api_request`; exclusive waste allocation)

```sql
ref AS (SELECT model, APPROX_QUANTILES(cost_usd, 2)[OFFSET(1)] AS ref_cost
        FROM v_api_calls WHERE is_agent AND call_rank > 1 AND <date filter> GROUP BY model)
SELECT c.*,
  IF(NOT c.is_agent, c.cost_usd, 0)                                            AS overhead,
  IF(c.is_agent AND c.call_rank = 1, GREATEST(c.cost_usd - IFNULL(r.ref_cost, c.cost_usd), 0), 0) AS cold_excess,
  IF(c.is_agent AND t.is_friction, c.cost_usd - <cold_excess>, 0)              AS friction,
  c.cost_usd - <overhead> - <cold_excess> - <friction>                         AS useful
FROM v_api_calls c LEFT JOIN v_turns t USING (prompt_id) LEFT JOIN ref r USING (model)
```

Each call's cost lands in exactly one ordered bucket (overhead → cold-start excess → friction → useful), so the segments never overlap and sum to the total. Assertion in the test suite: `ABS(SUM(overhead+cold_excess+friction+useful) − SUM(cost_usd)) < 1e-9`.

**`v_sessions`** (grain: `session_id`): person, surface, version, `start_ts`, `end_ts`, `n_turns`, `n_friction`, `agent_cost`, `overhead_cost`, `cold_excess`, `cache_hit = cache_read/(cache_read+input+cache_creation)`, `active_s` (SUM of `active_time.total` deltas), `start_type`, `lines_added/removed`, `edits_accept/reject`, `models ARRAY`.

**`v_person_day`** (grain: user × day): squad, surface, sessions, turns, friction turns (both variants), rejects, corrections, abandoned, agent/overhead/cold-excess cost, tokens by type, median prompt length, active seconds, lines +/−, edit accept/reject, flags `uses_mcp`, `uses_auto`, `uses_resume`. Every page-level KPI aggregates from here, except per-turn distributions.

**`v_tool_health`** (grain: day × tool_name × squad): calls, failures, p50/p95 duration, mean sizes, fail time, `mcp_server = REGEXP_EXTRACT(tool_name, r'^mcp__(.+?)__')`.

**`v_mcp_conn`** (grain: day × user × status × transport_type × error_code): attempts, `SUM(duration_ms)`. No server column (see 6.2b).

**`v_squad_k`**: squad, `active_headcount`, `display_squad = IF(active_headcount >= k_anon_min, squad, 'other')`. Every exec and cross-squad aggregate groups by `display_squad` (§8.2).

**`v_heuristic_quality`**: joins `heuristic_labels` with `v_turns` on `prompt_id` and `heuristic_version`. Outputs `n_labelled`, `precision_correction = COUNTIF(correction_kw AND true_is_correction) / COUNTIF(correction_kw)`, `recall_correction`, `category_accuracy`, and the confusion matrix. Shown on the admin view and in the definitions drawer.

**`v_insights`**: a single `UNION ALL` of the rule queries in §6. Each one emits `insight_key, rule, scope_type, scope_id, evidence JSON, action, impact_usd_month, impact_turns_month, impact_seconds_month, uses_kw BOOL`.

### 4.3 Heuristics (v1, `heuristic_version = 'kw-2'`)

Implemented as one Python function at ingest. The prompt is lowercased and NFC-normalised, and all regexes use Python `re` on `str` (Unicode-aware `\b`, so `não` and `função` behave correctly). Unit-tested with a fixture of ≥ 40 labelled PT/EN prompts that includes the v1 false positives: `não altere X`, `precisa`, `decisão`, `escrever`, `crítico`, `específico`, `address`, `docker`, `no caso`, `ainda não existe`.

**Fast re-prompt window:** the next `user_prompt` in the same session starts less than `config.fast_reprompt_s` (60 s) after the previous turn's last event. The session timeline (4.2) shows gaps so the threshold can be audited.

**Auxiliary exclusion:** `api_request` with `query_source NOT IN ('sdk','main')` (observed: `prompt_suggestion`, `generate_session_title`, `auxiliary`) is overhead. It is left out of the turn model mix, the context baseline, cold-start cost and per-turn quality. In cost totals it is its own "overhead" segment (1.8). Unknown future `query_source` values default to overhead and are listed on 6.3. The same rule applies to `assistant_response` when it carries a `query_source`.

**Category (first match wins; all patterns are word-boundary regex):**

| Priority | Category | Regex (`re.I`) |
|---|---|---|
| 1 | `bugfix` | `\b(fix(es|ed|ing)?|bugs?|erros?|errors?|quebr\w*|falh\w*|traceback|exceptions?|stack ?trace|broken|crash\w*)\b`, `\bnão (está )?funciona\w*`, `\bdoesn'?t work\b` |
| 2 | `test` | `\b(tests?|testes?|testar|testing|pytest|jest|vitest|coverage|cobertura|specs?|unit ?tests?)\b` |
| 3 | `refactor` | `\b(refactor\w*|refator\w*|simplif\w*|clean ?up|limpa[rr]?|renome\w*|rename\w*|extract\w*|extrai[rr]?)\b` |
| 4 | `review` | `\b(review\w*|revis[aeã]\w*|code ?review|audit\w*)\b` |
| 5 | `ops` | `\b(commit\w*|push|merge\w*|deploy\w*|docker\w*|git|prs?|pull request|ci|cd|pipelines?|gcloud|terraform|kubectl|helm)\b` |
| 6 | `docs` | `\b(readme|docs?|documenta\w*|document(ation)?|changelog|docstrings?|coment[aá]rios?|comments?)\b` |
| 7 | `feature` | `\b(add|adicion\w*|implement\w*|cri[ae]r?|criei|create|build|nov[ao]s?|new|feature)\b` |
| 8 | `question` | text ends with `?`, or `^(como|o que|por ?que|qual|quais|why|what|how|explain|explica\w*)\b` |
| 9 | `other` | nothing matched |

**Correction cue (`correction_kw`, the only tone label that affects KPIs):** look only at the first 5 tokens (split on whitespace). True if any of these match:

| Pattern | Why it is safe |
|---|---|
| `^(não|nao|no|nope)\s*[,.!;:]` | bare negation only when punctuation follows ("não, faz X"); `não altere X` does not match |
| `\b(não|nao) (é|era|foi) (isso|assim)\b`, `\bisso não\b`, `\bnot (that|this|what)\b`, `\bthat'?s not\b` | explicit rejection phrases |
| `\b(errad[oa]|wrong|incorret[oa]|incorrect)\b` | — |
| `\b(de novo|again|outra vez)\b`, `\bainda (não|nao|está|esta|dá|da|continua)\b`, `\bstill (not|broken|failing|wrong)\b`, `\bcontinua (dando|com|quebr\w*|falh\w*)\b` | `ainda`/`still` only together with a failure word |
| `\b(na verdade|actually|instead|em vez|ao invés)\b` | redirection |
| `\b(desfa[zç]\w*|undo|revert\w*|volta[r]? (atrás|o que))\b` | rollback request |

**Other tones (display only, never in KPIs):** `frustration` = `!!` or more, or ≥ 50% uppercase letters with length ≥ 10, or a short PT/EN profanity list kept in code. `positive` = `\b(obrigad[oa]|valeu|thanks?|perfeito|perfect|ótimo|great|boa)\b`. Otherwise `neutral`.

**Validation gate:**

1. Sampling: `scripts/sample_for_labels.py` draws 60 turns stratified 50/50 by `correction_kw`. The text for those turns is pulled by an admin with access reason `heuristic-validation`, which is logged. The sample includes only people who opted in to text capture.
2. A labeller fills `true_is_correction`, `true_category` and `true_is_friction` in a CSV. It is loaded into `heuristic_labels`. No text is stored there.
3. `v_heuristic_quality` computes precision. When `n_labelled ≥ 50` and `precision_correction ≥ 0.8`, an admin writes `kw_validated=true`, `kw_label_n`, `kw_precision_correction`, `kw_validated_at` and `kw_validated_by` to `config`. This is a deliberate human sign-off.
4. While `kw_validated=false`, or when `heuristic_version` changes, every widget listed under the beta rule (§3) carries `beta`, and insights with `uses_kw` are ranked below insights without it. If precision stays under 0.8 after tuning, the exec tiles switch to the behavioural-only clean-turn rate.

When the LLM judge (`lib/detection/classify_feedback`) lands, it writes `heuristic_version='llm-1'` to the same `derived` field and goes through the same gate.

### 4.4 Squad attribution

`squad = COALESCE(people.squad, team_attr, 'unassigned')`. `OTEL_RESOURCE_ATTRIBUTES=team=<squad>` is only a fallback for people missing from `people`.

### 4.5 Ingest and hosting

Two Cloud Run services built from **one image**, region `southamerica-east1`. `APP_ROLE` selects the routes:

| Service | `APP_ROLE` | Access | Routes |
|---|---|---|---|
| `darwinloop-ingest` | `ingest` | `--allow-unauthenticated`. The app checks `Authorization: Bearer <token>` against Secret Manager secret `darwinloop-ingest-token` (constant-time compare; 401 otherwise) and rejects records whose `organization.id != config.org_id` | `POST /v1/logs`, `POST /v1/metrics` (OTLP/HTTP JSON) |
| `darwinloop-dashboard` | `dashboard` | IAP enabled, restricted to the Google Workspace domain. The app reads the `X-Goog-Authenticated-User-Email` header and verifies the IAP JWT (`X-Goog-IAP-JWT-Assertion`) | `GET /`, `GET /api/<widget>`, admin routes |

This deviates from context.md's "one service" on purpose: IAP applies to a whole service, and CLI/desktop OTLP exporters cannot complete Google sign-in. One image keeps deploys at a single build. Each service has its own service account: ingest has `bigquery.dataEditor` on the raw tables only; dashboard has `bigquery.dataViewer` plus `jobUser`, and write access only to `insight_status` and `access_log`. shortcut: one shared org token means telemetry identity is asserted by the client; upgrade to per-person tokens mapped to email if spoofing becomes a concern.

**Client setup** (distributed through managed settings `env` so people do not configure it by hand):

```
CLAUDE_CODE_ENABLE_TELEMETRY=1
OTEL_LOGS_EXPORTER=otlp
OTEL_METRICS_EXPORTER=otlp
OTEL_EXPORTER_OTLP_PROTOCOL=http/json
OTEL_EXPORTER_OTLP_ENDPOINT=https://<darwinloop-ingest URL>
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer <token>
OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta     # required
OTEL_RESOURCE_ATTRIBUTES=team=<squad>                        # optional fallback
OTEL_LOG_USER_PROMPTS=1                                      # opt-in, per person
```

**Metric temporality:** for every `sum` and `histogram`, the ingest reads `aggregationTemporality` (1 = DELTA, 2 = CUMULATIVE). DELTA points and gauges go to `raw_metrics`. CUMULATIVE points are **not stored**. They are counted into `ingest_rejects (reason='cumulative_temporality')`, and the response is HTTP 200 with OTLP `partialSuccess.rejectedDataPoints` and an error message naming the env var, so clients do not retry forever. The ingest stays stateless. 6.8 lists the affected people with the fix.

**Writes:** `insert_rows_json` (streaming) per request, batched per table. Rows sit in the streaming buffer for up to ~90 minutes, which matters for deletion (§8). `prompt` and `response` attributes are split into `raw_text` with `user_id`/`user_email` and removed from `attrs` before the `raw_events` insert. Records whose `user.id` is in `deleted_subjects` are dropped (counted in `ingest_rejects`).

### 4.6 Build plan (one engineer, ~5 working days)

- **Day 1:** image with both roles, ingest (auth, temporality check, text split, heuristics kw-2 + fixture tests), raw tables, `deploy.sh` (both services, secret, IAP, service accounts).
- **Day 2:** views (`v_api_calls`, `v_turns`, `v_cost_alloc` with the sum assertion, `v_sessions`, `v_person_day`, `v_squad_k`, `v_tool_health`, `v_mcp_conn`, `v_heuristic_quality`).
- **Day 3:** API layer (parametrised SQL, response shape with `sql`/`n` for the drawer) + pages 01–03.
- **Day 4:** pages 04–06, roles, access log, k-anon, bands.
- **Day 5:** insights R1, R2a, R2b, R4, R5, R7, R8, R9 + 7.1/7.2 + 1.11, empty states, mobile pass.
- **v1.1:** R3, R6, R10, R11, R12, 2.5, 3.4 scatter, 6.5, 6.7, survey loader.

Stack: Python (FastAPI) + `google-cloud-bigquery`; static HTML + vanilla JS + one chart library pinned from cdnjs. No Supabase.

---

## 5. Value / ROI (honest framing)

1. **Notional cost, never "savings" without a comparison.** `cost_usd` is the client's API-price estimate. With `plan_type='seat'`, every cost widget carries the suffix "notional", and the money actually paid is `seats_purchased × seat_usd_month`. With `plan_type='api'`, the same numbers are real spend and the suffix is dropped.
2. **Seat leverage (1.7)** answers "is the seat plan worth it": `SUM(cost_usd of A∪X in month m) / active_people_m / seat_usd_month`. High leverage means heavy users the seat is subsidising. Very low leverage means people to enable.
3. **Unused seats (1.12)** is the only figure on a seat plan that is real, reclaimable money: `GREATEST(seats_purchased − active_people_m, 0) × seat_usd_month`.
4. **Where spend goes (1.8)** uses an exclusive allocation and is always an upper bound (≤). "Cost in friction turns" is spend in turns that showed friction, not spend proven wasted. On seat plans, USD waste is reframed as "rate-limit headroom and latency", since it is not billed. Time lost (tool failures, MCP connects) is real on any plan.
5. **Verified savings from actions (1.11/7.2)** is the realised-savings rollup: the sum of before/after deltas of insights marked done, measured over ≥ 14 days after `done_at`, in USD (≤, notional on seat plans), friction turns and tool-wait hours. It is labelled "before/after, not causal". The net figure includes actions that made things worse.
6. **Prompt-quality improvement** is shown as a trend, not a score: 3.7 per person, 2.6 per squad. 3.7 shows the clean-turn rate and median prompt length per category week by week.
7. **Output proxies, labelled as proxies:** edit acceptance rate, lines added/removed, active time. They give context on 02–04 and are never productivity scores or rankings.
8. **Hours saved:** there is no telemetry figure. The only path is 1.13, **needs: survey** (monthly self-reported minutes saved per week per category, labelled "self-reported", aggregated with n ≥ k_anon_min), or **needs: GitHub/Jira** outcomes.
9. **Outcome slot (1.10):** `outcomes_github_pr` joined on author email → PR cycle time and PRs per active dev, split by "AI-heavy week" (person above the squad median of active days) vs not. `outcomes_jira_issue` → lead time by squad. The views already `LEFT JOIN` these tables, and the card shows the "connect" CTA until rows exist.

---

## 6. Actionable insights (rules in `v_insights`)

Each rule needs ≥ 14 days of data and the low-data minimums, and each one emits a concrete action. Prices come from `model_tiers` list prices for token-type-specific impacts (R1, R3), because `cost_usd` is not split by token type. If no matching `model_tiers` row exists, the rule still fires but its impact shows "—" and it ranks by turns affected.

**v1 (5-day build): R1, R2a, R2b, R4, R5, R7, R8, R9.** v1.1: R3, R6, R10, R11, R12 (specified here so the data model supports them).

| Rule | Trigger | Scope | Recommended action | Impact estimate |
|---|---|---|---|---|
| R1 Context bloat | median `cache_read_tokens` of the first A call per turn > 80k | person / squad | Run `/context` to see what fills the baseline. Trim CLAUDE.md, and disable unused plugins and MCP servers (MCP servers seen in that scope's tool calls are listed from 6.2a) | `(median − 40k) × agent_turns_month × list_usd_per_mtok_cache_read / 1e6` (≤) |
| R2a Broken MCP server | an MCP server's tool calls (6.2a) fail > 50% with ≥ 5 calls, or p95 tool duration > 5 s with ≥ 5 calls | server × squad | Fix or disable MCP server `<server>` in settings (`claude mcp remove <server>` or the project `.mcp.json`) | fail time per month (s) from 6.2a |
| R2b MCP connection failures (server unknown) | a person's `mcp_server_connection` failure rate > 50% with ≥ 5 attempts in 14 days | person (visible to the person and their manager; exec sees the org count) | Run `/mcp` in Claude Code to find the server that fails to connect, then fix or remove it. The server name is not in telemetry | `time_lost_s` per month from 6.2b |
| R3 Over-powered model (v1.1) | share of agent cost on `tier='large'` for categories `question`, `docs`, `ops` > 50%, n ≥ 20 turns | squad / person | Model downgrade: set the default model for those workflows to the `medium` tier; keep `large` for `bugfix`/`feature` | `large_cost × (1 − medium_price / large_price)` (≤). `medium_price` = observed cost per turn of `medium` tier in scope over the last 28 days if ≥ 20 turns, else the `model_tiers` list price ratio. **Suppressed** when neither exists |
| R4 Permission friction | `user_reject` rate on a tool > 20% with ≥ 10 decisions | tool × squad | Add explicit allow/deny rules in project `settings.json`, and a CLAUDE.md rule on when that tool must not be used | rejects per month avoided |
| R5 Category failure `beta` | friction rate for a category ≥ 1.5× the squad overall, n ≥ 20 | category × squad | Write a CLAUDE.md rule or a skill for that workflow (e.g. "how we run tests here"); link the 5 worst turns as evidence (derived fields for managers) | friction turns per month |
| R6 Thin prompts (v1.1) `beta` | person's friction rate for `<80`-char prompts ≥ 2× their `300–1000` bucket, n ≥ 10 each | person (visible to the person and their manager) | Coaching: share the prompt template (goal, files, constraints, done-criteria) | friction turns per month |
| R7 Cold-start tax | person's `cold_share` > 40% and ≥ 50% of sessions with ≤ 2 turns | person | Coaching: resume sessions (`claude --continue` / `--resume`), batch related tasks in one session | `SUM(cold_excess)` per month (≤) |
| R8 Overhead | overhead share (1.8) > 10% | org / person | Disable prompt suggestions in settings | overhead cost per month |
| R9 Adoption gap | squad penetration < 50%, or a person not activated 14 days after `start_date` | squad / person | Enablement session; pair the person with a `power` user from 02 | headcount not activated (and `× seat_usd_month` on seat plans) |
| R10 Stale client (v1.1) | person on a version older than latest − 2 minor | person | Update Claude Code (managed settings or `claude update`) | — |
| R11 Tool failures (v1.1) | tool failure rate > 30% with ≥ 20 calls | tool × squad | Fix the environment (missing binary, path, hook); add a SessionStart hook or a CLAUDE.md setup note | fail time per month |
| R12 Abandonment (v1.1) | abandoned turns > 10% of a person's turns, n ≥ 20 | person | Coaching session reviewing 3 abandoned turns; check whether R4 or R11 apply | abandoned turns |

Ranking for 1.9 / 7.1: `impact_usd_month` where defined, else `impact_turns_month × median agent cost per turn`, else `impact_seconds_month` converted at the median turn duration. Insights with `uses_kw` rank below the others while the gate is closed. Ties go to the broader scope (org > squad > person). Person-scoped insights never appear on exec views (§8).

---

## 7. Visual layout (DarwinLoop identity)

### 7.1 Tokens

```
--bg:        #0A0A0A   page background
--surface:   #141414   cards, table header            (derived: bg +4% L)
--border:    #262626   1px card / table borders        (derived)
--text:      #FAFAFA
--muted:     #A1A1A1   secondary text, axis labels     (derived)
--primary:   #8ED563   good / clean / main series
--accent:    #199953   links, secondary series
--cta:       #23F884   buttons (text #0A0A0A)
--warn:      #E5B341   warning threshold, "beta" chip  (addition, not in brand)
--bad:       #F25F5C   friction / failure              (addition, not in brand)
--lowdata:   #3A3A3A   greyed low-n values

font-body:   Inter 400/600
font-mono:   JetBrains Mono 400/600 — all numbers, KPIs, labels, chips, table numerics, page numbers
radius:      0 (cards, charts); 4px buttons and chips
shadow:      none
space:       4px base; card padding 16px; grid gap 16px; side gutter 16px mobile / 32px desktop
```

Charts: categorical series use `--primary`, `--accent` and `--muted` in that order, never more than 3 hues per chart; status uses `--primary`/`--warn`/`--bad`. Axes and gridlines use `--border`. Bands render as text chips (`low`/`typical`/`high`) in `--muted`/`--text`/`--warn`, never as numbers. The `beta` chip is a 4px-radius outline in `--warn`, JetBrains Mono 11px. Dark only in v1 (brand is dark-only); every text/background pair meets WCAG AA (≥ 4.5:1). Page titles use the brand's numbered-step style: `01 Overview` … `07 Insights` in JetBrains Mono, with the number in `--primary`.

### 7.2 Wireframes

**Frame (all pages)**

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [logo] DarwinLoop  01 Overview  02 Squads  06 Health  07 Insights   you@ ▾  │
├──────────────────────────────────────────────────────────────────────────────┤
│ [28d ▾ 2026-09-24 → 2026-10-22] [month: 2026-09 ▾] [squad ▾] [surface ▾] [model ▾] │
│ Org / Platform / Ana / 3f9c… / turn 12                                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

**01 Overview**

```
01 Overview
┌────────────┬────────────┬──────────────┬────────────┬────────────┬──────────────┐
│ WAU    def │ PENETRATION│ CLEAN [beta] │ $/ACTIVE/WK│ UNUSED SEATS│ VERIFIED SAVED│
│ 23  ▲+4    │ 68%        │ 81%  ▲2pp    │ $14        │ 6 · $600/mo │ ≤$210/mo     │
│ ▁▂▃▅▆▇     │ 23/34      │ behav. 86%   │ notional   │ 34 − 28     │ 38 turns·2.1h│
│            │            │ n=1,942      │            │ (2026-09)   │ 3 of 4 done  │
└────────────┴────────────┴──────────────┴────────────┴────────────┴──────────────┘
┌───────────────────────────────┬───────────────────────────────┐
│ 1.3 ADOPTION BY SQUAD         │ 1.7 SEAT LEVERAGE (2026-09)    │
│ Platform ██████████ 90% 9/10  │ Org      ───●──|──   0.9       │
│ Data     ██████░░░░ 60% 6/10  │ Platform ─────|─●─   1.4       │
│ Mobile   ███░░░░░░░ 30% 3/10  │ Data     ─●───|───   0.4       │
│ other(<5)██░░░░░░░░ 25%       │      seat price = 1.0 ┘        │
├───────────────────────────────┼───────────────────────────────┤
│ 1.4 DEPTH (active days / 28d) │ 1.8 WHERE SPEND GOES (≤, notional)│
│ 1    ███                      │ [useful 71%|friction-turns 12% │
│ 2-5  ██████                   │  |cold excess 12%|overhead 5%] │
│ 6-12 ████████                 │  $1,204 · $203 · $198 · $84    │
│ 13+  ██████                   │                                │
├───────────────────────────────┼───────────────────────────────┤
│ 1.4b REACH  MCP 41% auto 22%  │ 1.4c NEW JOINERS  median 3 days │
│      resume 57%               │      2 of 7 not yet started     │
├───────────────────────────────┴───────────────────────────────┤
│ 1.9 TOP ACTIONS                                                │
│ 01  Fix or disable MCP "jira-local" — its tools failed 34/34   │
│     calls, 6 min waited/mo · Data squad               [view →] │
│ 02  Trim context: baseline 112k tokens/call · org ≤$96/mo      │
│                                                       [view →] │
│ 03  Enablement for Mobile — 7 of 10 not activated     [view →] │
│     also: MCP connects failing on 4 machines, 41 min/mo lost,  │
│     server unknown → run /mcp                                  │
├────────────────────────────────┬───────────────────────────────┤
│ 1.10 OUTCOMES needs: GitHub ·  │ 1.13 TIME SAVED needs: survey  │
│ needs: Jira       [connect →]  │ (self-reported)   [set up →]  │
└────────────────────────────────┴───────────────────────────────┘
```

**02 Squad**

```
02 Squad · Data
┌──────────┬──────────────┬──────────┬──────────┐
│ WAU 6/10 │ CLEAN 74%    │ $11/wk   │ EDIT ACC │
│          │ [beta] n=402 │ notional │ 88%      │
└──────────┴──────────────┴──────────┴──────────┘
┌───────────────────────────────────────────────────────────────┐
│ 2.2 PEOPLE      (bands vs squad: low / typical / high)        │
│ name   last   days turns mcp auto  $/wk    corr    rej  status│
│ Carla   —       0     0   ·   ·     —       —       —   not activ.│
│ Bruno  10-21    6    88   ·   ✓   typical  high   high  struggling│
│ Ana    10-22   14   311   ✓   ✓   high     low    low   power  │
├──────────────────────────────┬────────────────────────────────┤
│ 2.3 FRICTION BY CATEGORY beta│ 2.4 FRICTION MIX (flags/week)   │
│ test     ████████ 41% n=58   │ ▇ reject ▇ tool ▇ fast ▇ corr   │
│ bugfix   █████ 27%  n=120    │ ▆▆ ▇▅ ▆▆ ▅▅                     │
│ feature  ███ 18%    n=140    │                                 │
├──────────────────────────────┴────────────────────────────────┤
│ 2.6 TREND (12w)  clean ── behavioural ┄┄  WAU ▁▂▃              │
└───────────────────────────────────────────────────────────────┘
```

**03 Person**

```
03 Person · Bruno (Data)                 visible to: Bruno, Data manager · viewed by (2)
┌────────┬──────────┬────────┬────────┬────────┐
│ DAYS 6 │CLEAN 61% │TURN/SES│ LEN 64 │ $9/wk  │   tick = squad median
│ |──●   │ ●──| beta│ 1.8 ●| │ ●──|   │  ─●|   │
└────────┴──────────┴────────┴────────┴────────┘
┌──────────────────────────────┬────────────────────────────────┐
│ 3.7 WEEKLY TREND (12w) beta  │ 3.3 PROMPT LENGTH vs FRICTION   │
│ clean  ▁▂▂▃▄▅  (sq ┄┄)       │ <80     ████████ 48%  sq 30%   │
│ len/bugfix  60→140 chars     │ 80-300  ████ 22%      sq 20%   │
│ len/test    45→ 90 chars     │                                 │
├──────────────────────────────┼────────────────────────────────┤
│ 3.4 COLD-START TAX  44%      │ 3.6 TOOLS                       │
│ short sessions 61%           │ Bash  120  fail 8%  rej 15%     │
│                              │ Edit   90  fail 1%  rej 2%      │
├──────────────────────────────┴────────────────────────────────┤
│ 3.2 CALENDAR (28d)  ░▒▓░ ░▒▒ ▓░░ ...                           │
├───────────────────────────────────────────────────────────────┤
│ 3.5 SESSIONS                                                   │
│ start  surface turns fric  $   +/-     type   model     [→]    │
├───────────────────────────────────────────────────────────────┤
│ 3.8 WHAT YOUR MANAGER SEES                                     │
│ Bruno 10-21 6 88 · ✓ typical high high struggling              │
└───────────────────────────────────────────────────────────────┘
```

**04 Session / 05 Turn**

```
04 Session 3f9c… · Bruno · cli 2.1.4 · 14:02→14:41 · fresh · $0.62 · cache 91%
┌───────────────────────────────────────────────────────────────┐
│ 4.2 TIMELINE  [t1 ████]12s[t2 █]8s[t3 ██████]240s[t4 ███]      │
│               green=clean  red=friction  grey=abandoned        │
├──────────────────────────────┬────────────────────────────────┤
│ 4.3 COST / TURN (cold|agent|ovh)│ 4.4 CONTEXT / CALL ─ 100k ref │
└──────────────────────────────┴────────────────────────────────┘

05 Turn 3 · bugfix · 64 chars · kw-2 [beta]          [fast_reprompt 8s] [user_reject]
┌───────────────────────────────────────────────────────────────┐
│ 5.1 PROMPT   "roda o teste de novo"            (text expires 11-21)│
│ 5.2 WATERFALL                                                  │
│ #1 api_request  sonnet  in 3k  cache 104k  $0.01  ttft 900ms   │
│ #2 tool_decision Bash  reject  user_reject                     │
│ —  no tool_result, no assistant_response                       │
│ 5.5 NEXT → turn 4 · 8s later · correction [beta]               │
└───────────────────────────────────────────────────────────────┘
```

**06 Health**

```
06 Health
┌──────────────────────────────┬────────────────────────────────┐
│ 6.1 TOOLS                    │ 6.2a MCP SERVERS (from tool calls)│
│ tool  calls fail p95  failtime│ server     calls fail p95  people│
│ Bash  1.2k  6%  4.1s  9m     │ jira-local   34  100% 8.9s   4   │
├──────────────────────────────┼────────────────────────────────┤
│ 6.2b MCP CONNECTIONS (server │ 6.3 API LATENCY p50/p95 ttft    │
│ unknown) 212 att · 31% fail  │ ─── sonnet  ┄┄ opus   errors ▁▂ │
│ 41 min lost · by error_code  │                                 │
│ needs: server name attr      │                                 │
├──────────────────────────────┼────────────────────────────────┤
│ 6.4 PERMISSION POSTURE (k≥5) │ 6.6 CONTEXT BASELINE  112k      │
│ Platform [config|accept|rej] │ Platform ███ 98k  Data ████ 131k│
├──────────────────────────────┴────────────────────────────────┤
│ 6.8 INGEST HEALTH (admin) 2 clients send cumulative metrics    │
└───────────────────────────────────────────────────────────────┘
```

**07 Insights** is a single column of cards. Each card has an `NN  <action>` headline in JetBrains Mono, an evidence line in `--muted`, impact right-aligned, an optional `beta` chip, and buttons `[evidence →] [mark done] [dismiss]`. Cards marked done show the 7.2 before/after mini bars and the delta that feeds 1.11.

Mobile (< 768px): the grid collapses to one column. KPI rows become 2 × 3. Tables become stacked cards showing name + 3 key values with a "more" expander. The filter bar collapses into one `[filters (3)]` button. No horizontal page scroll; wide tables scroll inside their own card. The definitions drawer becomes a bottom sheet.

---

## 8. Privacy and access

### 8.1 Roles

Identity is Google sign-in via IAP on the `darwinloop-dashboard` service, domain-restricted. The role comes from `people.role`.

| Viewer | Org/squad aggregates | Person page | Session / turn derived fields | Prompt/response text |
|---|---|---|---|---|
| `dev` | yes (k-anon, §8.2) | own only | own only | own only |
| `manager` | own squad: full. Other squads: k-anon only | people where `people.manager_email = viewer`, or the same squad when `squad_lead`. Cost, correction, reject and clean rates are shown as **bands**; badges, adoption flags and coaching insights by name | same scope, derived fields only | **no** |
| `exec` | yes, k-anon only | **no** (blocked with lock) | no | no |
| `admin` | yes | yes, every access logged | yes, logged | only with a recorded reason (support, incident, `heuristic-validation`), logged |

### 8.2 k-anonymity (one rule everywhere)

Any squad-level aggregate shown to an exec, or to a manager looking at a squad that is not theirs, groups by `v_squad_k.display_squad`. Squads with `active_headcount < config.k_anon_min` (5) are merged into "other". If "other" itself has fewer than `k_anon_min` people, it is suppressed and shows "hidden (< k)". This applies to 1.3, 1.7, 1.13, 6.4, 6.6, the squad drill on 1.4b, and any squad breakdown in 06/07. Org-wide numbers are shown when the org has ≥ `k_anon_min` active people. The person-name column in 6.2a/6.2b is replaced by a count for these viewers.

### 8.3 Other rules

- **Access log:** every person, session or turn view writes `access_log(viewer_email, target_user_id, level, ts, reason)`. The person sees who viewed their page (03 header "viewed by", 3.8).
- **Text is never shown to managers or execs.** Coaching uses derived signals (category, tone, flags, lengths). Prompt text is the most sensitive field: it may contain client data, credentials pasted by mistake, or personal remarks.
- **Retention:** `raw_text` partition expiration is 30 days, enforced by BigQuery, not by app code. `raw_events`/`raw_metrics` are kept 400 days, `access_log` 400 days, `ingest_rejects` 90 days. Dataset time travel is set to 48 hours. BigQuery also keeps a 7-day fail-safe that cannot be configured; the team notice states this. Prompt capture is opt-in per person via `OTEL_LOG_USER_PROMPTS=1`. Without it, the dashboard works on derived fields only (5.1 shows "text not captured").
- **Ingest minimisation:** telemetry does not send file paths or command content, and the ingest stores none. `user.email` is stored only in `raw_events.user_email`, `raw_text.user_email`, `raw_metrics.user_email` and `people`. URLs and exports use `user_id` hashes.
- **Purpose limitation** (in the dashboard footer and the team notice): the data is used to improve AI tooling, enablement and cost. It is **not** used for individual performance evaluation, ranking or compensation. There is no leaderboard. The 02 people table is sorted by status (who needs help), not by volume, and shows bands, not exact per-person numbers.

### 8.4 LGPD notes

- **Legal basis:** legitimate interest (art. 7, IX) for tooling improvement and cost governance, with a documented legitimate-interest assessment (LIA). Prompt text capture also relies on transparency and opt-in.
- **Transparency (art. 9):** a team notice before rollout, in plain Portuguese, describing the signals collected, purposes, retention (including the 48 h time travel and 7-day fail-safe), and who sees what (§8.1–8.3).
- **Data subject rights (art. 18):** a person can view their own data (03–05, 3.8), request an export (CSV of their `v_turns`/`v_sessions`), and request deletion. SLA: 15 days.
- **Deletion procedure** (admin, `scripts/erase_subject.py`, logged):
  1. Insert `user_id` and `email_sha256` into `deleted_subjects`. From then on the ingest drops new records, and every view hides the person immediately.
  2. Wait until the person's last streamed row is older than 90 minutes, so the streaming buffer has flushed. BigQuery rejects `DELETE` on rows still in the buffer.
  3. Run `DELETE ... WHERE user_email = @e OR user_id = @id` on `raw_events`, `raw_text`, `raw_metrics`, `survey_responses`; delete the `people` row and `heuristic_labels` rows for their turns; set `insight_status.owner_email` to NULL where it is theirs.
  4. `access_log`: rows where they are the **target** keep the access record (accountability for who accessed data, art. 37), but `target_user_id` is replaced with `deleted:<random>`. Rows where they are the **viewer** are deleted.
  5. Verify that a `COUNT(*)` per table is 0; if not (buffer), retry after 90 minutes. Set `completed_at`. The data is unrecoverable once time travel (48 h) and fail-safe (7 days) pass, which is inside the SLA.
- **Minimisation and storage limitation:** 30-day text, aggregates beyond that. No sensitive personal data categories are intended to be collected, and the tone heuristic does not infer health, religion, etc.
- **Location:** the dataset is in `southamerica-east1` (data stays in Brazil). Processor: Google Cloud (DPA via GCP terms). Anthropic receives prompts as part of normal product use, which this dashboard does not change.
- **Controller/DPO:** name the Brain3 encarregado in the notice. **needs: DPO contact** before rollout.
