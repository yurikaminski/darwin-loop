# DarwinLoop AI Usage Dashboard — Spec v1

Status: draft v1 (design loop iteration 1). Source of truth for signals: `docs/dashboard/context.md`.
Scope: Claude Code CLI (`service.name=claude-code`) and desktop Code tab (`claude-code-desktop`) only. Cowork, claude.ai chat and Office agents are out of scope.

Rule used throughout: if a number cannot be computed from the OTLP signals in context.md plus the `people` and `config` tables, it is marked **needs: <source>** and rendered as an empty slot, never estimated.

---

## 1. Personas and the questions they answer

| Persona | Primary page | Questions (each maps to a widget below) |
|---|---|---|
| **Exec / AI value owner** (owns adoption + value metrics) | 01 Overview, 07 Insights | Is AI actually adopted, and is it growing? Which squads lag? What does it cost per active person, and is the seat plan worth it vs API pricing? Where is money/time wasted (context bloat, broken MCP, wrong model)? Which 3 actions move the needle this month? What outcome evidence do we have (needs GitHub/Jira)? |
| **Eng manager / tech lead** | 02 Squad, 06 Health, 07 Insights | Who on my squad is not activated or is struggling (high friction) and needs coaching? Which task categories fail most (tests? refactors?) so I can add a CLAUDE.md rule or skill? Which tools/MCP servers break? Are people approving everything (governance) or rejecting a lot (bad permissions)? |
| **Individual dev** | 03 Person (self), 04 Session, 05 Turn | Where do my turns go wrong? Are my prompts too short for the category? Am I paying a cold-start tax by opening many short sessions? What do my best sessions look like? |

Personas map to `people.role` values: `exec`, `manager`, `dev`, `admin`. Access rules in section 8.

---

## 2. Navigation and drill-down model

```
Org (01 Overview) ──> Squad (02) ──> Person (03) ──> Session (04) ──> Turn (05)
       │                  │               │
       └── 06 Health ─────┴── 07 Insights ┘   (both filterable to squad/person, each row links into the hierarchy)
```

**Global filter bar** (sticky, top of every page; state lives in the URL query string so every view is a shareable link):

| Filter | Values | Source field |
|---|---|---|
| `from`, `to` | date range, default last 28 days, presets 7/28/90d | `event_ts` (UTC, displayed America/Sao_Paulo) |
| `squad` | multi-select from `people.squad`; `unassigned` bucket | `people.squad`, fallback resource attr `team` |
| `surface` | `cli`, `desktop`, all | `service.name` |
| `model` | multi-select of observed `model` | `api_request.model` |

URL scheme: `/?from=&to=&squad=&surface=&model=`, `/squad/<squad>`, `/person/<email_hash>`, `/session/<session_id>`, `/turn/<prompt_id>`. Persons are addressed by `user.id` hash in URLs, never by email.

**Drill rules (every aggregate links down):**

- Any KPI tile → the chart that decomposes it on the same page, or the next level filtered to the tile's scope.
- Any chart bar/point keyed by squad → `/squad/<squad>` with the same filters; keyed by person → `/person/<id>`; keyed by day → same page with `from=to=<day>`.
- Any table row: squad → 02, person → 03, session → 04, turn → 05, tool → 06 filtered to tool, insight → the evidence list (sessions/turns) behind it.
- Breadcrumb always shows `Org / <squad> / <person> / <session> / <turn>` with filters carried over.
- Drill is blocked (lock icon + reason) when the viewer lacks the role for the target level (section 8).

---

## 3. Pages and widgets

Notation: `T` = set of turns in filter scope (from `v_turns`), `S` = sessions, `P` = people in scope from `people` (active=true), `A` = agent API calls (`query_source IN ('sdk','main')`), `X` = overhead API calls (any other `query_source`). Rates show `n` next to them. **Low-data rule (global):** a rate with denominator < 20 turns (or < 3 people) renders grey with "n=<k>, low data" and is excluded from rankings and insights.

### 01 Overview (exec)

| # | Widget | Question | Chart | Metric definition | Drill target | Empty / low data |
|---|---|---|---|---|---|---|
| 1.1 | Weekly active users | Is it adopted? | KPI tile + 12-week sparkline | `WAU = COUNT(DISTINCT person) with ≥1 turn in the ISO week`; tile shows last full week and delta vs prior week | 1.3 | "No telemetry received yet" + link to setup doc |
| 1.2 | Penetration | What share of the team uses it? | KPI tile (%) | `WAU / COUNT(people WHERE active AND start_date <= week_end)`. Hidden if `people` is empty ("needs: people table") | 02 table sorted by penetration | needs: people table |
| 1.3 | Adoption by squad | Which squads lag? | Horizontal bar per squad, value = penetration, bar label = WAU/headcount | as 1.2 grouped by squad; squads with headcount < 3 merged into "other" | `/squad/<s>` | Squad with 0 WAU shown as empty bar, not hidden |
| 1.4 | Depth of use | Is it habitual or occasional? | Histogram: people by active days in last 28d (buckets 1, 2-5, 6-12, 13+) | `active_days = COUNT(DISTINCT DATE(turn.start_ts))` per person | click bucket → person list in 02 | — |
| 1.5 | Clean-turn rate | Is the AI doing what people asked? | KPI tile + weekly line | `1 - friction_rate`; `friction_rate = COUNT(T WHERE is_friction) / COUNT(T)` (definition in 4.3) | 02 friction by squad | low-data rule |
| 1.6 | Notional cost per active person | What does a user cost? | KPI tile (USD/week) + seat comparison text | `SUM(cost_usd over A∪X) / WAU` for the week. Subtitle: "notional on seat plans; seat = $<config.seat_usd_month>/month" | 1.8 | — |
| 1.7 | Seat leverage | Is the seat plan paying off vs API pricing? | Bullet chart per squad: notional API cost/person/month vs seat price line | `leverage = SUM(cost_usd)/active_people_month / config.seat_usd_month`. >1 = seat cheaper than API would be; <0.3 = seat underused | 02 person table sorted by leverage | Hidden when `config.plan_type='api'` (then show real spend instead) |
| 1.8 | Waste breakdown | Where is spend wasted? | Stacked bar (single, 100%): agent-useful, cold-start, overhead (aux calls), friction turns | `overhead = SUM(cost X)`; `cold_start = SUM(cost of first A call per session) - median(cost of non-first A calls)*sessions`; `friction_cost = SUM(cost A in turns WHERE is_friction)`; remainder = useful. Each segment is an upper-bound label "≤" | segment → 07 filtered to that waste type | — |
| 1.9 | Top 3 actions | What do I do this month? | Ranked list (from `v_insights`, top 3 by impact) | see section 6 | insight evidence | "No actionable patterns yet (needs ≥ 2 weeks of data)" |
| 1.10 | Outcomes | Did delivery improve? | Slot card | **needs: GitHub** (PR cycle time, PRs/active dev), **needs: Jira** (lead time). `pull_request.count` / `commit.count` metrics shown if ever received (documented, not yet observed) | — | Empty slot with "connect GitHub" CTA |

Cut as vanity: total prompts, total tokens, total lines of code as headline numbers. They appear only as context inside drill pages.

### 02 Squad (manager)

| # | Widget | Question | Chart | Metric definition | Drill | Empty / low data |
|---|---|---|---|---|---|---|
| 2.1 | Squad KPI row | Health at a glance | 4 tiles: WAU/headcount, clean-turn rate, notional cost/active person/week, edit acceptance | Edit acceptance = `SUM(code_edit_tool.decision WHERE decision='accept') / SUM(code_edit_tool.decision)` | tiles → 2.2 sorted by that column | low-data rule |
| 2.2 | People table | Who needs help? | Table, one row per person in squad (including inactive) | columns: name, last active date, active days (28d), turns, clean-turn rate, correction rate, reject rate, median prompt length, sessions, turns/session, notional cost, status badge (`not activated` = 0 turns since start_date+14d; `struggling` = friction_rate ≥ squad median + 15pp with n ≥ 20; `power` = active days ≥ 13) | row → `/person/<id>` | Inactive people listed with "0" not hidden (adoption gap is the point) |
| 2.3 | Friction by category | Which kinds of work fail? | Horizontal bar per prompt category: friction rate, bar width = turn count | `friction_rate` grouped by `turn.category` | bar → 04 session list filtered to turns of that category with friction | category with n < 20 greyed |
| 2.4 | Friction mix | Why do turns fail? | Stacked weekly bars: user_reject / tool failure / fast re-prompt / correction keyword / abandoned | counts of each flag over T (a turn can carry several flags; stacked shows flag counts, labelled as such) | segment → turn list | — |
| 2.5 | Model mix vs category | Are we using the right model? | Heatmap: rows = category, cols = model, value = share of agent cost | `SUM(cost A) by category, model / SUM(cost A) by category` | cell → turn list | — |
| 2.6 | Squad trend | Getting better? | Line: weekly clean-turn rate and WAU, 12 weeks | as above per week | point → same page week range | < 3 weeks: show table instead of line |

### 03 Person (self, or manager of person's squad)

| # | Widget | Question | Chart | Metric definition | Drill | Empty |
|---|---|---|---|---|---|---|
| 3.1 | Person KPI row | How am I doing vs my squad? | 5 tiles each with squad median as a tick: active days, clean-turn rate, turns/session, median prompt length, notional cost/week | from `v_person_day` | — | < 5 turns: "Not enough activity yet" |
| 3.2 | Activity calendar | When do I use it? | 28-day calendar heatmap, value = turns/day | `COUNT(T) per day` | day → 3.5 filtered to day | — |
| 3.3 | Prompt length vs friction | Do short prompts hurt me? | Bar: friction rate by prompt length bucket (<80, 80-300, 300-1000, >1000 chars), person vs squad | `friction_rate` grouped by `length_bucket(prompt_length)` | bucket → turn list | bucket n < 10 greyed |
| 3.4 | Cold-start tax | Am I opening too many short sessions? | KPI + scatter: sessions by turns (x) vs cost (y) | `cold_share = SUM(first A call cost per session) / SUM(cost A)`; short session = ≤ 2 turns | point → `/session/<id>` | — |
| 3.5 | Sessions table | Which sessions went well / badly? | Table | start, surface, duration (from `active_time.total` if present else last-first event), turns, friction turns, notional cost, lines +/-, start_type (fresh/resume), main model | row → `/session/<id>` | — |
| 3.6 | Tool profile | Which tools do I depend on and reject? | Table per tool_name | calls, failure rate, user rejects, p95 duration | row → 06 filtered to tool+person | — |

### 04 Session

| # | Widget | Question | Chart | Metric definition | Drill | Empty |
|---|---|---|---|---|---|---|
| 4.1 | Session header | What happened? | Text row | person, surface, version, os, start/end, start_type, permission modes seen (`permission_mode_changed`), total notional cost, cache hit ratio | — | — |
| 4.2 | Turn timeline | Where did it go wrong? | Horizontal timeline, one block per turn, width = duration, color = clean (`--primary`) / friction (`--bad`) / abandoned (`--muted`); gaps between turns labelled in seconds (fast re-prompts visible as < 60s gaps) | from `v_turns` ordered by `start_ts` | block → `/turn/<prompt_id>` | — |
| 4.3 | Cost per turn | Was the first turn the expensive one? | Bar per turn: agent cost stacked with overhead cost | `SUM(cost A)`, `SUM(cost X)` per turn | bar → turn | — |
| 4.4 | Context size per call | Is context bloated? | Line: `cache_read_tokens + input_tokens + cache_creation_tokens` per A call, with 100k reference line | raw per `api_request` | — | — |
| 4.5 | Outcome strip | What did it produce? | Text: lines added/removed, edit accept/reject counts | `lines_of_code.count`, `code_edit_tool.decision` for session | — | "no edits" |

### 05 Turn

| # | Widget | Question | Chart | Metric definition |
|---|---|---|---|---|
| 5.1 | Prompt | What was asked? | Text block + labels (category, tone, length, heuristic_version) | prompt text from `raw_text` (only if ≤ 30 days old and viewer allowed, section 8); otherwise "text expired, derived fields only" |
| 5.2 | Event waterfall | What did the agent do? | Waterfall rows ordered by `event.sequence`: api_request (model, tokens, cost, ttft), tool_decision (accept/reject + source), tool_result (tool, success, duration, sizes), assistant_response (length) | all events with this `prompt.id` |
| 5.3 | Friction flags | Why is it flagged? | Chips: `user_reject`, `tool_fail`, `fast_reprompt (<Ns)`, `correction_next`, `abandoned` | flags from `v_turns` with the evidence event linked |
| 5.4 | Response | What did it answer? | Collapsed text block | `assistant_response.response` from `raw_text`, same access rules as 5.1 |
| 5.5 | Next turn | How did the user react? | Link card to next turn with gap seconds and its tone label | `LEAD()` over session |

### 06 Health & Governance (manager, admin; exec sees aggregates)

| # | Widget | Question | Chart | Metric definition | Drill | Empty |
|---|---|---|---|---|---|---|
| 6.1 | Tool reliability | Which tools break? | Table: tool_name, calls, failure rate, p50/p95 duration, avg result size | `tool_result` grouped by `tool_name`; `failure_rate = COUNT(success=false)/COUNT(*)` | row → turns with that tool failing | — |
| 6.2 | MCP servers | Which MCP servers are broken or slow? | Table: server (from `tool_name` prefix `mcp__<server>__` and `mcp_server_connection`), connect attempts, connect failure rate, p95 connect ms, error codes, time lost | `time_lost_s = SUM(duration_ms WHERE status!='connected')/1000` | row → sessions affected | "no MCP connections observed" |
| 6.3 | API latency and errors | Is the model side slow? | Lines: p50/p95 `ttft_ms` and `duration_ms` per day per model; error count bar | `api_request`, `api_error` count. Error breakdown by status: **needs: observed api_error shape** (v1 shows count only) | day → sessions | — |
| 6.4 | Permission posture | Are people auto-approving everything? | Stacked bar per squad: share of tool_decisions by `source` (`config` vs user accept vs `user_reject`); plus count of `permission_mode_changed` to auto | `COUNT(tool_decision) by source / total` | squad → 02 | — |
| 6.5 | Client versions | Is anyone on an old client? | Table: `service.version` × people count, flag versions older than latest seen − 2 minor | latest `service.version` per person (last 7d) | row → person list | — |
| 6.6 | Context baseline | How heavy is our default context? | KPI + per-squad bar: median `cache_read_tokens` per A call on first-call-of-turn | `APPROX_QUANTILES(cache_read_tokens,2)[1]` | squad → persons sorted by baseline | — |
| 6.7 | Plugin/config inventory | What is installed? | Table: plugin name × people count from `plugin_loaded`; managed settings present (yes/no per person) | `plugin_loaded`, `managed_settings_resolved` | — | "none observed" |

### 07 Insights

| # | Widget | Question | Chart | Metric definition | Drill |
|---|---|---|---|---|---|
| 7.1 | Action list | What should we do? | Card list sorted by impact; each card = rule name, scope (org/squad/person), evidence numbers, recommended action, est. impact, status (open/done/dismissed, stored in `insight_status`) | rows of `v_insights` (section 6) | card → evidence turns/sessions |
| 7.2 | Done tracker | Did the action work? | Before/after mini chart for each insight marked done: rule's trigger metric 14 days before vs after `done_at` | trigger metric recomputed in two windows | — |

---

## 4. Derived data model (BigQuery `brain003-mvp.darwinloop_telemetry`, `southamerica-east1`)

### 4.1 Raw tables (written by the Cloud Run ingest)

| Table | Grain | Key columns | Partition / retention |
|---|---|---|---|
| `raw_events` | one OTLP log record | `event_ts TIMESTAMP`, `ingest_ts`, `event_name`, `session_id`, `prompt_id`, `event_sequence INT64`, `user_id`, `user_email`, `account_uuid`, `org_id`, `service_name`, `service_version`, `os_type`, `host_arch`, `terminal_type`, `team_attr` (resource `team`), `env_attr`, `attrs JSON` (all event attributes **minus** `prompt` and `response`), `derived JSON` (`category`, `tone`, `correction_kw`, `length_bucket`, `heuristic_version`; only on `user_prompt`) | `PARTITION BY DATE(event_ts)`, `CLUSTER BY user_email, session_id`, partition expiration 400 days |
| `raw_text` | one prompt or response text | `event_ts`, `session_id`, `prompt_id`, `event_sequence`, `kind` (`prompt`/`response`), `text STRING` | `PARTITION BY DATE(event_ts)`, **partition expiration 30 days** |
| `raw_metrics` | one OTLP data point | `ts`, `metric_name`, `value FLOAT64`, `user_email`, `session_id`, `service_name`, `attrs JSON` (type, decision, source, tool_name, language, start_type) | `PARTITION BY DATE(ts)`, 400 days. Store deltas: the ingest converts cumulative sums to deltas per (series, start_time) |
| `people` | one person | `email`, `user_id_hash`, `name`, `squad`, `role` (`exec`/`manager`/`dev`/`admin`), `manager_email`, `start_date`, `active BOOL` | none; edited manually (CSV load) |
| `config` | key/value | `plan_type` (`seat`/`api`), `seat_usd_month`, `fast_reprompt_s` (60), `min_turns_rate` (20), `k_anon_min` (5) | none |
| `insight_status` | insight id | `insight_key`, `status`, `owner_email`, `done_at`, `note` | none |
| `outcomes_*` (slot) | per PR / issue | **needs: GitHub** (`outcomes_github_pr`: author_email, opened_at, merged_at, additions, deletions), **needs: Jira** (`outcomes_jira_issue`) | out of v1; views LEFT JOIN them when present |

Why text is split: partition expiration deletes whole partitions, so text must live in its own table for the 30-day rule while events survive. Category/tone are computed at ingest so they outlive the text.

### 4.2 Derived views

All views are plain views in v1. shortcut: plain views re-scan raw tables on every load, upgrade to scheduled `MERGE` into tables when `raw_events` passes ~10 GB or page load > 3 s.

**`v_person`** — `people` LEFT JOIN identities seen in `raw_events` on email; `squad = COALESCE(people.squad, team_attr, 'unassigned')`. Emails seen in telemetry but missing from `people` appear with squad `unassigned` and role `dev`.

**`v_api_calls`** — `raw_events WHERE event_name='api_request'`, unpacks `model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, cost_usd, duration_ms, ttft_ms, query_source, effort`, adds `is_agent = query_source IN ('sdk','main')` and `call_rank = ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY event_ts)` restricted to agent calls (first agent call = cold start).

**`v_turns`** (grain: `prompt_id`)

| Column | Definition |
|---|---|
| `start_ts` | `event_ts` of `user_prompt` |
| `end_ts` | `MAX(event_ts)` over all events with this `prompt_id` |
| `prompt_length`, `category`, `tone`, `correction_kw`, `length_bucket` | from `user_prompt` attrs/derived |
| `n_agent_calls`, `agent_cost`, `overhead_cost`, `input/output/cache_read/cache_creation tokens` | from `v_api_calls` split by `is_agent` |
| `main_model` | model with the largest agent cost in the turn |
| `n_tool_calls`, `n_tool_fail` | `tool_result` count, count `success=false` |
| `n_user_reject` | `tool_decision WHERE source='user_reject'` (or `decision='reject'` and source != `config`) |
| `has_response` | any `assistant_response` with `query_source IN ('sdk','main')` or missing query_source |
| `next_gap_s` | `TIMESTAMP_DIFF(LEAD(start_ts) OVER (PARTITION BY session_id ORDER BY start_ts), end_ts, SECOND)` |
| `next_correction_kw` | `LEAD(correction_kw)` over the same window |
| `is_fast_reprompt` | `next_gap_s IS NOT NULL AND next_gap_s < config.fast_reprompt_s` |
| `is_abandoned` | `NOT has_response AND next_gap_s IS NULL` (last turn of session ended without an answer) |
| `is_friction` | `n_user_reject > 0 OR n_tool_fail > 0 OR is_fast_reprompt OR next_correction_kw OR is_abandoned` |

Friction rate (canonical): `COUNTIF(is_friction) / COUNT(*)` over `v_turns`. Correction rate: `COUNTIF(next_correction_kw)/COUNT(*)`. Reject rate: `COUNTIF(n_user_reject>0)/COUNT(*)`.

Note for v1 tuning: `n_tool_fail > 0` will over-flag (an agent often recovers from a failed grep). The 7.2 tracker and a weekly sample review of 20 flagged turns decide whether to raise it to `n_tool_fail >= 2` or "failure with no later success of the same tool".

**`v_sessions`** (grain: `session_id`): person, surface (`service_name`), version, `start_ts = MIN`, `end_ts = MAX`, `n_turns`, `n_friction`, `agent_cost`, `overhead_cost`, `first_call_cost` (agent `call_rank=1`), `cache_hit = cache_read/(cache_read+input+cache_creation)`, `active_s` (SUM `claude_code.active_time.total` for session), `start_type` (from `claude_code.session.count`), `lines_added/removed` (`lines_of_code.count` by type), `edits_accept/reject` (`code_edit_tool.decision`), `models ARRAY`.

**`v_person_day`** (grain: email × day): squad, surface, sessions, turns, friction turns, rejects, corrections, abandoned, agent/overhead cost, tokens by type, median prompt length, active seconds, lines +/-, edit accept/reject. All page-level KPIs aggregate from here except per-turn distributions.

**`v_tool_health`** (grain: day × tool_name × squad): calls, failures, p50/p95 duration, mean sizes; MCP rows add `mcp_server = REGEXP_EXTRACT(tool_name, r'^mcp__([^_]+(?:_[^_]+)*)__')` joined with `mcp_server_connection` counts.

**`v_insights`** — one `UNION ALL` of rule queries (section 6), each emitting `insight_key, rule, scope_type, scope_id, evidence JSON, action, impact_usd_month, impact_note`.

### 4.3 Heuristics (v1, `heuristic_version = 'kw-1'`)

**Fast re-prompt window:** next `user_prompt` in the same session starting < `config.fast_reprompt_s` (default 60 s) after the previous turn's last event. Rationale: reading and judging a response plus writing a considered follow-up rarely fits in 60 s; a quick "no, do X" does. Configurable; the session timeline (4.2) shows gaps so the threshold can be audited.

**Auxiliary exclusion:** `api_request` with `query_source NOT IN ('sdk','main')` (observed: `prompt_suggestion`, `generate_session_title`, `auxiliary`) is overhead. Overhead is excluded from: turn model mix, context baseline, cold-start cost, per-turn quality. It is included in cost totals as its own "overhead" segment (1.8). Unknown future `query_source` values default to overhead and are listed on 6.3 so nothing is silently counted as agent work. Same rule for `assistant_response` when it carries `query_source`.

**Category (first match wins, prompt lowercased, PT + EN):**

| Priority | Category | Keywords / regex |
|---|---|---|
| 1 | `bugfix` | `fix`, `bug`, `erro`, `error`, `quebr`, `falh`, `traceback`, `exception`, `stack trace`, `não funciona`, `doesn't work`, `broken` |
| 2 | `test` | `test`, `teste`, `pytest`, `jest`, `coverage`, `cobertura`, `spec` |
| 3 | `refactor` | `refactor`, `refator`, `simplif`, `clean up`, `limp`, `renome`, `rename`, `extract` |
| 4 | `review` | `review`, `revis`, `code review`, `audit` |
| 5 | `ops` | `commit`, `push`, `merge`, `deploy`, `docker`, `git `, ` pr `, `pull request`, `ci`, `pipeline`, `gcloud`, `terraform` |
| 6 | `docs` | `readme`, `doc`, `documen`, `comment`, `changelog` |
| 7 | `feature` | `add`, `adicion`, `implement`, `cri`, `create`, `build`, `nova`, `new` |
| 8 | `question` | ends with `?`, or starts with `como`, `o que`, `por que`, `why`, `what`, `how`, `explain`, `explica` |
| 9 | `other` | none matched |

**Tone (applied to the prompt; `correction_kw` is true when tone = `correction`):**

| Tone | Rule |
|---|---|
| `correction` | starts with or contains as a word: `não`, `nao`, `no`, `errado`, `wrong`, `de novo`, `again`, `ainda`, `still`, `na verdade`, `actually`, `instead`, `em vez`, `desfaz`, `undo`, `revert`, `volta`, `isso não` |
| `frustration` | `!!` or more, or ≥ 50 % uppercase letters with length ≥ 10, or a small profanity list (kept in code, PT+EN) |
| `positive` | `obrigad`, `valeu`, `thanks`, `perfeito`, `perfect`, `ótimo`, `great`, `boa` |
| `neutral` | otherwise |

Heuristics run in the ingest (Python, one function, unit-tested with a fixture of ~30 labelled prompts). When the LLM judge (`lib/detection/classify_feedback`) lands, it writes `heuristic_version='llm-1'` into the same `derived` field; dashboards filter on the latest version available per turn.

---

## 5. Value / ROI (honest framing)

What v1 can show, and what it labels:

1. **Notional cost, never "savings" without a counterfactual.** `cost_usd` is the client's API-price estimate. With `config.plan_type='seat'` every cost widget carries the suffix "notional" and the money actually paid is `seat_usd_month × active seats`. With `plan_type='api'`, the same numbers are real spend and the suffix is dropped.
2. **Seat leverage (1.7)** answers "is the seat plan worth it": notional API cost per person-month / seat price. High leverage = heavy users the seat is subsidising; very low leverage = seats to reclaim or people to enable. This is the only ROI-like ratio v1 asserts.
3. **Waste (1.8, 7.1)** is computed as recoverable notional cost or recoverable time (MCP failures, slow tools), always as an upper bound (≤). On seat plans waste in USD is reframed as "rate-limit headroom and latency", since cost is not billed; time lost is real on any plan.
4. **Output proxies, labelled as proxies:** edit acceptance rate, lines added/removed, active time. They are shown on 02–04 for context, never as productivity scores or rankings.
5. **Hours saved: not shown.** No telemetry signal measures counterfactual time. **needs: survey** (periodic self-reported minutes saved per task category) or **needs: GitHub/Jira** outcomes.
6. **Outcome slot (1.10):** `outcomes_github_pr` joined on author email → PR cycle time and PRs per active dev, split by "AI-heavy week" (person above squad median active days) vs not; `outcomes_jira_issue` → lead time by squad. Views already `LEFT JOIN` these tables; the card renders the "connect" CTA until rows exist. `commit.count` / `pull_request.count` OTel metrics are picked up automatically if Claude Code starts emitting them.

---

## 6. Actionable insights (rules in `v_insights`)

Every rule needs ≥ 14 days of data and the low-data minimums; every rule emits a concrete action. Impact formulas use observed prices from `v_api_calls` (cost per token derived per model as `SUM(cost_usd)/SUM(tokens)` weighted), not a hardcoded price list.

| Rule | Trigger | Scope | Recommended action | Impact estimate |
|---|---|---|---|---|
| R1 Context bloat | median first-call `cache_read_tokens` > 80k | person / squad | Trim CLAUDE.md, disable unused plugins and MCP servers (list from 6.7 for that person) | `(baseline − 40k) × agent_calls × cache_read_price` per month (≤) |
| R2 Broken MCP | MCP server connect failure rate > 50 % over ≥ 5 attempts, or p95 connect > 5 s | server × squad | Disable or fix MCP server `<name>` in settings | time lost per month (s) from 6.2 |
| R3 Over-powered model | share of agent cost on the top-tier model for categories `question`, `docs`, `ops` > 50 % | squad / person | Model downgrade: set default model for those workflows to a smaller model (settings `model`), keep top tier for `bugfix`/`feature` | `cost × (1 − smaller_price/top_price)` (≤) |
| R4 Permission friction | `user_reject` rate on a tool > 20 % with ≥ 10 decisions | tool × squad | Add explicit allow/deny rules in project `settings.json`, and a CLAUDE.md rule stating when that tool must not be used | rejects per month avoided |
| R5 Category failure | friction rate for a category ≥ 1.5× squad overall with n ≥ 20 | category × squad | Write a CLAUDE.md rule or a skill for that workflow (e.g. "how we run tests here"); link the 5 worst turns as examples | friction turns per month |
| R6 Thin prompts | person's friction rate for `<80` char prompts ≥ 2× their `300-1000` bucket, n ≥ 10 each | person (visible to person + manager) | Coaching: share prompt template (goal, files, constraints, done-criteria) | friction turns per month |
| R7 Cold-start tax | person's `cold_share` > 40 % and ≥ 50 % sessions with ≤ 2 turns | person | Coaching: resume sessions (`claude --continue`/`--resume`), batch related tasks in one session | `first_call_cost − median_call_cost` × short sessions (≤) |
| R8 Overhead | overhead cost share > 10 % | org / person | Disable prompt suggestions in settings | overhead cost per month |
| R9 Adoption gap | squad penetration < 50 % or person not activated 14 days after `start_date` | squad / person | Enablement session, pair the person with a `power` user from 02 | headcount not activated |
| R10 Stale client | person on a version older than latest − 2 minor | person | Update Claude Code (managed settings or `claude update`) | — |
| R11 Tool failures | tool failure rate > 30 % with ≥ 20 calls | tool × squad | Fix environment (missing binary, path, hook); add a SessionStart hook or CLAUDE.md note for setup | failed calls per month |
| R12 Abandonment | abandoned turns > 10 % of a person's turns, n ≥ 20 | person | Coaching session reviewing 3 abandoned turns; check if R4/R11 apply | abandoned turns |

Ranking for 1.9 / 7.1: `impact_usd_month` where defined, else turns-per-month affected × median turn cost; ties broken by scope breadth (org > squad > person). Person-scoped insights never appear on the exec view (section 8).

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
--warn:      #E5B341   warning threshold               (addition, not in brand)
--bad:       #F25F5C   friction / failure              (addition, not in brand)
--lowdata:   #3A3A3A   greyed low-n values

font-body:   Inter 400/600
font-mono:   JetBrains Mono 400/600 — all numbers, KPIs, labels, chips, table numerics, page numbers
radius:      0 (cards, charts); 4px buttons and chips
shadow:      none
space:       4px base; card padding 16px; grid gap 16px; side gutter 16px mobile / 32px desktop
```

Charts: categorical series use `--primary`, `--accent`, `--muted` in that order, never more than 3 hues per chart; status uses `--primary`/`--warn`/`--bad`. Axis and gridlines `--border`. Light mode is not offered in v1 (dark-only brand); all text/background pairs meet WCAG AA (≥ 4.5:1). Page titles use the brand numbered-step style: `01 Overview`, `02 Squad`, …, `07 Insights`, rendered in JetBrains Mono with `--primary` number.

### 7.2 Wireframes

**Frame (all pages)**

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [logo] DarwinLoop  01 Overview  02 Squads  06 Health  07 Insights   you@ ▾  │
├──────────────────────────────────────────────────────────────────────────────┤
│ [28d ▾ 2026-09-24 → 2026-10-22] [squad: all ▾] [surface: all ▾] [model ▾]   │
│ Org / Platform / Ana / 3f9c… / turn 12                                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

**01 Overview**

```
01 Overview
┌────────────┬────────────┬────────────┬────────────┐
│ WAU        │ PENETRATION│ CLEAN TURNS│ $/ACTIVE/WK│
│ 23  ▲+4    │ 68%        │ 81%  ▲2pp  │ $14 notional│
│ ▁▂▃▅▆▇     │ 23/34      │ n=1,942    │ seat $100/m│
└────────────┴────────────┴────────────┴────────────┘
┌───────────────────────────────┬───────────────────────────────┐
│ 1.3 ADOPTION BY SQUAD         │ 1.7 SEAT LEVERAGE              │
│ Platform ██████████ 90% 9/10  │ Platform ───●────|──           │
│ Data     ██████░░░░ 60% 6/10  │ Data     ─●──────|──           │
│ Mobile   ███░░░░░░░ 30% 3/10  │          seat price ┘          │
├───────────────────────────────┼───────────────────────────────┤
│ 1.4 DEPTH (active days / 28d) │ 1.8 WASTE (≤, notional)        │
│ 1   ███                       │ [useful 71%|cold 12%|fric 12%| │
│ 2-5 ██████                    │  ovh 5%]                       │
│ 6-12 ████████                 │                                │
│ 13+ ██████                    │                                │
├───────────────────────────────┴───────────────────────────────┤
│ 1.9 TOP ACTIONS                                                │
│ 01  Disable MCP "jira-local" — fails 100% of connects, 41 min  │
│     lost/mo · Data squad                              [view →] │
│ 02  Trim context: baseline 112k tokens/call · org     [view →] │
│ 03  Enablement for Mobile — 7 of 10 not activated     [view →] │
├────────────────────────────────────────────────────────────────┤
│ 1.10 OUTCOMES   needs: GitHub · needs: Jira    [ connect → ]   │
└────────────────────────────────────────────────────────────────┘
```

**02 Squad**

```
02 Squad · Data
┌──────────┬──────────┬──────────┬──────────┐
│ WAU 6/10 │ CLEAN 74%│ $11/wk   │ EDIT ACC │
│          │ n=402    │ notional │ 88%      │
└──────────┴──────────┴──────────┴──────────┘
┌───────────────────────────────────────────────────────────────┐
│ 2.2 PEOPLE                                                    │
│ name   last   days turns clean corr rej  len  $/wk  status    │
│ Ana    10-22   14   311  86%   4%   2%   410  $18  power      │
│ Bruno  10-21    6    88  61%  19%   9%    64  $9   struggling │
│ Carla   —       0     0   —     —    —     —   —   not activ. │
├──────────────────────────────┬────────────────────────────────┤
│ 2.3 FRICTION BY CATEGORY     │ 2.4 FRICTION MIX (weekly)       │
│ test     ████████ 41% n=58   │ ▇ reject ▇ tool ▇ fast ▇ corr  │
│ bugfix   █████ 27%  n=120    │ ▆▆ ▇▅ ▆▆ ▅▅                     │
│ feature  ███ 18%    n=140    │                                 │
├──────────────────────────────┴────────────────────────────────┤
│ 2.5 MODEL × CATEGORY (share of agent cost)                     │
│            opus   sonnet  haiku                                │
│ question   ▓▓ 72%  ░ 28%   ·                                   │
└───────────────────────────────────────────────────────────────┘
```

**03 Person**

```
03 Person · Bruno (Data)                         visible to: Bruno, Data manager
┌────────┬────────┬────────┬────────┬────────┐
│ DAYS 6 │CLEAN61%│TURN/SES│ LEN 64 │ $9/wk  │   tick = squad median
│ |──●   │ ●──|   │ 1.8 ●| │ ●──|   │  ─●|   │
└────────┴────────┴────────┴────────┴────────┘
┌──────────────────────────────┬────────────────────────────────┐
│ 3.2 CALENDAR (28d)           │ 3.3 PROMPT LENGTH vs FRICTION   │
│ ░▒▓░ ░▒▒ ▓░░ ...             │ <80     ████████ 48%  sq 30%   │
│                              │ 80-300  ████ 22%      sq 20%   │
├──────────────────────────────┼────────────────────────────────┤
│ 3.4 COLD-START TAX  44%      │ 3.6 TOOLS                       │
│ $ ·  ·                       │ Bash  120  fail 8%  rej 15%     │
│   · ·  ·   turns →           │ Edit   90  fail 1%  rej 2%      │
├──────────────────────────────┴────────────────────────────────┤
│ 3.5 SESSIONS                                                   │
│ start  surface turns fric  $   +/-     type   model     [→]    │
└───────────────────────────────────────────────────────────────┘
```

**04 Session / 05 Turn**

```
04 Session 3f9c… · Bruno · cli 2.1.4 · 14:02→14:41 · fresh · $0.62 · cache 91%
┌───────────────────────────────────────────────────────────────┐
│ 4.2 TIMELINE  [t1 ████]12s[t2 █]8s[t3 ██████]240s[t4 ███]      │
│               green=clean  red=friction  grey=abandoned        │
├──────────────────────────────┬────────────────────────────────┤
│ 4.3 COST / TURN              │ 4.4 CONTEXT / CALL   ─ 100k ref │
└──────────────────────────────┴────────────────────────────────┘

05 Turn 3 · bugfix · correction · 64 chars                [fast_reprompt 8s] [user_reject]
┌───────────────────────────────────────────────────────────────┐
│ 5.1 PROMPT   "não, roda o teste de novo"     (text expires 11-21)│
│ 5.2 WATERFALL                                                  │
│ #1 api_request  sonnet  in 3k  cache 104k  $0.01  ttft 900ms   │
│ #2 tool_decision Bash  reject  user_reject                     │
│ —  no tool_result, no assistant_response                       │
│ 5.5 NEXT → turn 4 · 8s later · tone correction                 │
└───────────────────────────────────────────────────────────────┘
```

**06 Health and 07 Insights** follow the same grid: 06 = 2-column cards (tool table, MCP table / latency lines, permission posture / versions, context baseline / inventory); 07 = single column of insight cards, each `NN  <action>` headline in JetBrains Mono, evidence line in `--muted`, impact right-aligned, buttons `[evidence →] [mark done] [dismiss]`.

Mobile (< 768px): grid collapses to one column, tables become stacked cards showing name + 3 key numbers with "more" expander, filter bar collapses into one `[filters (3)]` button. No horizontal page scroll; wide tables scroll inside their own card.

### 7.3 Build shape (one engineer, ~5 days)

- One Cloud Run service (Python): `POST /v1/logs`, `POST /v1/metrics` (OTLP/HTTP JSON, bearer token in `OTEL_EXPORTER_OTLP_HEADERS`), heuristics at ingest, BigQuery streaming inserts; `GET /api/<widget>` runs parametrized SQL against the views; static HTML + vanilla JS + one chart library from CDN.
- Day 1 ingest + raw tables + heuristics with tests. Day 2 views. Day 3 pages 01–03. Day 4 pages 04–06 + auth/roles. Day 5 insights rules, empty states, mobile pass.

---

## 8. Privacy and access

**Roles (from `people.role`, identity = Google sign-in via IAP on Cloud Run, domain-restricted):**

| Viewer | Org/squad aggregates | Person page | Session / turn derived fields | Prompt/response text |
|---|---|---|---|---|
| `dev` | yes (k-anonymity applies) | own only | own only | own only |
| `manager` | yes | people where `people.manager_email = viewer` or same squad if flagged `squad_lead` | same scope | **no** (derived fields only) |
| `exec` | yes, squads with ≥ `k_anon_min` (5) people; smaller squads merged into "other" | **no** (blocked with lock) | no | no |
| `admin` | yes | yes, every access logged | yes, logged | only with a recorded reason (support/incident), logged |

- Access log: every person/session/turn view writes `access_log(viewer_email, target_user_id, level, ts, reason)` to BigQuery; the person can see who viewed their page (03 header "viewed by").
- Text is never shown to managers or execs: coaching uses derived signals (category, tone, flags, lengths). Prompt text is the most sensitive field (may contain client data, credentials pasted by mistake, personal remarks).
- **Retention:** `raw_text` partition expiration 30 days (enforced by BigQuery, not by app code). `raw_events`/`raw_metrics` 400 days. `access_log` 400 days. Prompt capture is opt-in per machine via `OTEL_LOG_USER_PROMPTS=1`; without it the dashboard works on derived fields only (5.1 shows "text not captured").
- **Ingest minimisation:** the ingest drops nothing it does not need but stores no file paths or command content (telemetry does not send them); `user.email` is stored only in `raw_events.user_email` and `people`; URLs and exports use `user_id` hashes.
- **Purpose limitation (written into the dashboard footer and team notice):** data is used to improve AI tooling, enablement and cost; it is **not** used for individual performance evaluation, ranking or compensation. No leaderboard exists; 02 people table is sorted by status (who needs help), not by volume.

**LGPD notes:**

- Legal basis: legitimate interest (art. 7, IX) for tooling improvement and cost governance, with a documented legitimate-interest assessment (LIA); prompt text capture additionally relies on transparency + opt-in.
- Transparency (art. 9): team notice before rollout describing signals collected, purposes, retention, who sees what (this section, in plain Portuguese).
- Data subject rights (art. 18): person can view their own data (03–05), request export (CSV of their `v_turns`/`v_sessions`) and deletion (`DELETE FROM raw_* WHERE user_email = ?`, run by admin, logged). Deletion request SLA 15 days.
- Minimisation and storage limitation: 30-day text, aggregates beyond; no sensitive personal data categories are intended to be collected; the tone heuristic does not infer health, religion, etc.
- Location: dataset in `southamerica-east1` (data stays in Brazil). Processor: Google Cloud (DPA in place via GCP terms); Anthropic receives prompts as part of normal product use, unchanged by this dashboard.
- Controller/DPO: name the Brain3 encarregado in the notice. **needs: DPO contact** before rollout.
