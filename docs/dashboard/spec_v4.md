# DarwinLoop AI Usage Dashboard — Spec v4

Status: draft v4 (design loop iteration 4). Source of truth for signals: `docs/dashboard/context.md`.
Scope: Claude Code CLI (`service.name=claude-code`) and desktop Code tab (`claude-code-desktop`) only. Cowork, claude.ai chat and Office agents are out of scope, and every seat-level number says so.

Rule used throughout: if a number cannot be computed from the OTLP signals in context.md plus the `people`, `config`, `model_tiers`, `heuristic_labels`, `heuristic_gate` and `survey_responses` tables, it is marked **needs: <source>** and rendered as an empty slot. It is never estimated.

Time zone rule: every day, ISO week, calendar month and 28-day window is cut in **America/Sao_Paulo** (`DATE(event_ts, 'America/Sao_Paulo')`, `DATE_TRUNC(d, ISOWEEK)`). Timestamps are stored in UTC.

### Changes from v3

| Area | v3 problem | v4 fix |
|---|---|---|
| Person identity | Keyed on `user.id`, which is a device or installation, so CLI + desktop users and two-laptop users were counted twice in WAU, penetration, depth, reach, seat leverage, 1.12, bands and person pages | `person_id = TO_HEX(SHA256(LOWER(TRIM(user.email))))`, fallback `SHA256('acct:' ‖ user.account_uuid)` when there is no email, computed once at ingest. Every `COUNT(DISTINCT …)`, `v_person`, `/person/<person_id>`, `access_log` and `deleted_subjects` use it. `user.id` survives only as `device_id` on events and sessions (§4.1, §4.5) |
| Live turns | `flag_abandoned` fired on turns still running or still being exported, biasing 1.5, 1.8, 2.4, R12 during working hours | `turn_state`: the last turn of a session whose last event is younger than `config.open_turn_grace_s` (1800 s) is `open`; all its flags and `is_friction_b` are NULL and it is outside `T_eval`, the denominator of every friction rate (§3, §4.2). 05/04 show an `in progress` chip |
| Window edges | `call_rank = 1` and `LEAD` inside a ±1 day pad created false cold calls, false session starts and false abandonment at the edges | No `call_rank`. `is_cold` = no previous agent call in the session within `cache_ttl_s` (the padded load always reaches ≥ 21 h back). `cold_reason` and `flag_abandoned` use fixed thresholds (`resume_gap_s` 6 h, `followup_window_s` 30 min) that are shorter than the look-back / look-ahead, so a turn gets the same flags whatever window it is read in. Per-session shape metrics use only sessions complete in the window. A window-stability test guards this (§4.2) |
| v1 scope | 5 days for one engineer was not credible; 1.11, 7.2 and `tvf_insight_attribution` carry the hardest SQL and show nothing at launch | 1.11 is a slot in v1 ("appears 14 days after the first action is marked done"); 7.2 and attribution move to v1.1. v1 rules: R1, R2a, R2b, R4, R7, R9 (R5, R8 → v1.1). Build plan re-estimated to **6 days**, with the role matrix, k-anon and bands on their own day (§4.6) |
| Adopted nice-to-haves | — | 1.14 adoption funnel on 01 (seats → telemetry → activated → WAU → habitual → deep). Overhead split into user-disablable (`prompt_suggestion`) and fixed (`generate_session_title`, `auxiliary`); R8 impact uses only the disablable share, settings key verified on Day 1. Dated gate ETA on 1.0. 2.2 bands need ≥ `k_anon_min` (5) qualifying people. 1.6/1.7 numerator = cost of the people counted as active, stated in the drawer. 1.15 output-proxy context line on 01. 6.2b server-name check is a Day 1 task |

Kept from v3: honest value framing (notional / API-equivalent, nothing called savings), drill-down to the turn with list views, `needs:` slots, per-person text opt-in at ingest, manager banding, k-anonymity, access log, erasure procedure, DarwinLoop tokens.

---

## 1. Personas and the questions they answer

| Persona | Primary page | Questions (each maps to a widget) |
|---|---|---|
| **Exec / AI value owner** (owns adoption and AI value metrics) | 01 Overview, 07 Insights | How much of the org does this data actually cover (1.0)? Is AI adopted, and is it growing (1.1, 1.2)? Is use deep or shallow (1.4, 1.4b)? Which squads lag (1.3)? Does the AI do what people asked (1.5)? What does a user cost, and what is the Claude Code share of the seat worth at API prices (1.6, 1.7)? How many seats show no Claude Code activity (1.12)? Where is spend wasted (1.8)? Which 3 actions matter this month (1.9)? Where do people drop out between seat and deep use (1.14)? What changed after the actions we took (1.11, slot until data exists)? What outcome evidence exists (1.10)? |
| **Eng manager / tech lead** | 02 Squad, 06 Health, 07 Insights | Who on my squad has not started, or may need support (2.2)? Which kinds of work fail most, so I can add a CLAUDE.md rule or a skill (2.3; R5 in v1.1)? Why do turns fail (2.4)? Which tools and MCP servers break (6.1, 6.2a, 6.2b)? Is the squad improving (2.6)? |
| **Individual dev** | 03 Person (self), 04 Session, 05 Turn | Where do my turns go wrong (3.3, 3.5)? Are my prompts too short for the kind of task (3.3, 3.7)? Am I paying a cache-cold tax (3.4)? Am I improving week over week (3.7)? What does my manager see about me (3.8)? |

Personas map to `people.role`: `exec`, `manager`, `dev`, `admin`. Access rules are in §8.

---

## 2. Navigation and drill-down model

```
Org (01) ──> Squad (02) ──> Person (03) ──> Session (04) ──> Turn (05)
   │             │              │               │
   └── 06 Health ┴─ 07 Insights ┴── /turns?…  /sessions?…  (filtered list views, §2.2)
```

### 2.1 Global filters and URLs

**Global filter bar** (sticky on every page; state lives in the URL query string, so every view is a shareable link):

| Filter | Values | Source field |
|---|---|---|
| `from`, `to` | date range, default last 28 days ending yesterday, presets 7/28/90d | `DATE(event_ts, 'America/Sao_Paulo')` |
| `month` | calendar month, used only by 1.7 and 1.12. Default: last complete month. The current month is allowed and labelled `MTD` | same |
| `squad` | multi-select from `v_person.squad`, including `unassigned` | `people.squad`, fallback resource attr `team` |
| `surface` | `cli`, `desktop`, all | `service.name` |
| `model` | multi-select of observed models | `api_request.model` |

Page URLs: `/?from=&to=&month=&squad=&surface=&model=`, `/squad/<squad>`, `/person/<person_id>`, `/session/<session_id>`, `/turn/<prompt_id>`, `/insights`, `/health`, plus the list views below. People are addressed by `person_id` (§4.5: one id per human across CLI, desktop and devices) in URLs and exports, never by email. `user.id` is a device id and never addresses a person.

### 2.2 List views (`/turns`, `/sessions`)

Two generic list pages. Every "row →", "bar →" and "segment →" drill that does not open a single entity opens one of these. They share one component and one API (`/api/list/turns`, `/api/list/sessions`).

**Filter params** (all optional, combinable with the global filters; unknown params → 400):

| Param | Values | Applies to |
|---|---|---|
| `person` | `person_id` | both |
| `session` | `session_id` | turns |
| `week` | ISO week start date `YYYY-MM-DD` (overrides `from`/`to`) | both |
| `day` | `YYYY-MM-DD` (self and admin only; managers get 403 for `day`) | both |
| `category` | `bugfix`, `test`, `refactor`, `review`, `ops`, `docs`, `feature`, `question`, `other`, `unknown` (= no text) | turns |
| `length_bucket` | `lt80`, `80-300`, `300-1000`, `gt1000` | turns |
| `flag` | `friction` (behavioural), `clean`, `user_reject`, `tool_fail`, `fast_reprompt`, `correction`, `abandoned`, `cold`, `open` | turns; on sessions it means "session has ≥ 1 turn with the flag". `open` turns never match `friction`, `clean` or a friction flag |
| `tool` | `tool_name` | turns: turns with ≥ 1 `tool_result` of that tool (with `flag=tool_fail`: failing) |
| `mcp_server` | server parsed from `mcp__<server>__*` | both, same semantics as `tool` |
| `mcp_conn` | `failed` (+ optional `error_code`) | sessions with ≥ 1 failed `mcp_server_connection` |
| `insight_key` | key from `v_insights` | both: the evidence rows of that insight (`v_insight_evidence`) |
| `sort` | turns: `newest` (default), `cost_desc` (self/admin only); sessions: `newest` (default), `turns_asc`, `turns_desc` | — |
| `cursor` | opaque keyset cursor | both |

**Columns:**

| View | Self / admin | Manager (people in scope only) |
|---|---|---|
| `/turns` | date + time, person, session link, category (+ coverage), length bucket, flag chips, agent calls, tool calls / failures, main model, notional cost | date, person, session link, category, length bucket, flag chips, agent calls, tool calls / failures, main model. **No time of day, no cost** |
| `/sessions` | start date + time, person, surface, duration, turns, friction turns, failing tool calls (when `tool`/`mcp_server` set), start_type, main model, notional cost | date, person, surface, turns bucket (`1–2`, `3–10`, `11+`), friction band, failing tool calls, start_type, main model. **No start time, duration or cost** |

**Role gating:** `exec` → lock page ("individual lists are not available to the exec role", §8.1). `dev` → `person` is forced to self; any other value → 403. `manager` → rows are restricted to people in their scope (§8.1), any `person` outside it → 403, columns as above. `admin` → everything; every list request writes one `access_log` row per distinct `target_person_id` returned.

**Pagination:** keyset on `(start_ts DESC, id)`, 50 rows per page, `cursor` = base64 of the last row's key. A header shows the total count (`COUNT(*)` of the same filter) and the active filters as removable chips. Empty: "No turns match these filters" with a "clear filters" button.

### 2.3 Drill rules (every aggregate links down)

- A KPI tile opens the chart that breaks it down on the same page, or the next level filtered to the tile's scope.
- A bar or point keyed by squad → `/squad/<squad>`; by person → `/person/<id>`; by day or week → the same page with `from`/`to` set to that period (managers on person pages: week only).
- Table rows: squad → 02, person → 03, session → 04, turn → 05. Every other drill names a list URL in the widget table (§3).
- People-list drills from org widgets (1.4, 1.4b) open `/squad/<squad>?active_days=<bucket>` or `?missing=<mcp|auto|resume>` or `?funnel=<step>` (1.14). 2.2 accepts these params. For a manager the squad is their own; an admin picks the squad; an exec gets no drill (lock) and instead sees the bucket split by `display_squad` in the definitions drawer.
- The breadcrumb always shows `Org / <squad> / <person> / <session> / <turn>` and carries the filters along.
- When the viewer lacks the role for the target, the drill is blocked and shows a lock icon with the reason (§8). A squad merged into "other" for k-anonymity does not link down for exec or cross-squad viewers.
- **Definitions drawer:** every KPI tile and chart header has a `def` button. It opens a side drawer with the exact SQL that produced the number (returned by the API, not written separately), `n`, text coverage where relevant, `heuristic_version`, the gate status of every heuristic the number uses (§4.3), and data freshness (`MAX(ingest_ts)`). Each `/api/<widget>` response is `{rows, sql, params, n, coverage, heuristic_version, gate, generated_at}`, so the drawer cannot drift from the number.

---

## 3. Pages and widgets

**v1 ships:** 01 (minus 1.4c, 1.13; 1.11 as a slot), 02, 03 (minus 3.6), 04 (4.1, 4.2, 4.5 only), 05, list views, 06 (6.1, 6.2a, 6.2b), 07 (7.1 only), rules R1, R2a, R2b, R4, R7, R9. **v1.1:** 1.11 live, 7.2, `tvf_insight_attribution`, R5, R8, 1.4c, 1.13, 3.6, 4.3, 4.4, 6.3, 6.4, 6.6, 6.8, 6.9 (specified so the data model supports them).

Notation:
- `T`: turns in filter scope (from `tvf_turns`). `T_eval`: turns in `T` with `turn_state = 'closed'` (§4.2). `T_text`: turns in `T_eval` with `has_text`. `S`: sessions with ≥ 1 turn in scope; `S_complete`: sessions in `S` with every loaded event inside the window (§4.2).
- People: always `COUNT(DISTINCT person_id)`, never `user.id`/`device_id`.
- Every friction, clean, reject and flag rate uses `T_eval` (or `T_text`) as its denominator, so turns still in progress never count.
- `A`: agent API calls (`query_source IN ('sdk','main')`). `X`: overhead API calls (any other `query_source`).
- Rates always show `n` beside them.

### Global rules

**Low-data rule:** a rate whose denominator is under `config.min_turns_rate` (20) turns, or under 3 people, renders as `--muted` text with a `low data` chip (bars: hatched `--lowdata-mark` fill), with "n=<k>". It is left out of rankings, bands and insights.

**Text-coverage rule:** `category`, `correction_kw` and `next_correction_kw` exist only for turns whose prompt text was captured (opt-in, §8.3). For all other turns they are NULL.
1. Category-based and correction-based rates use `T_text` (or the matching subset) as denominator, never `T`.
2. Every such widget shows a coverage chip next to its title: `text: 38% of turns · 9 people`, where `coverage = COUNT(T_text) / COUNT(T_eval)` and people = `COUNT(DISTINCT person_id in T_text)`.
3. When coverage is under 20% of turns or under 3 people, the widget renders the low-data state with "needs: more people opted in to text capture".
4. Widgets that use text: 2.3, 2.4 `correction` segment, 3.3 (category split only), 3.7(b), 5.1, 5.4, R5. The headline quality metric (1.5) does **not** use text.

**Friction definitions (used everywhere, §4.2):**
- `is_friction_b` (behavioural): `user_reject OR tool_fail OR fast_reprompt OR abandoned`. Defined for every closed turn; NULL for `open` turns.
- `is_friction` (full): `is_friction_b OR next_correction_kw IS TRUE`. For text-less turns this equals `is_friction_b`; the drawer says so. Used only for per-turn chips and for rates over `T_text`.
- **Clean-turn rate** = `1 − COUNTIF(is_friction_b) / COUNT(T_eval)`. This is the only clean rate shown on exec tiles, bands and badges.

**Gate rule:** every number that depends on a heuristic signal carries a `beta` chip until that signal passes the gate in §4.3 (`heuristic_gate.validated`). Signals: `fast_reprompt`, `tool_fail`, `abandoned`, `correction`, `category`. `user_reject` is a direct human action and is not gated. The behavioural clean rate depends on `fast_reprompt`, `tool_fail` and `abandoned`, so it is `beta` until all three pass. The chip tooltip reads: "heuristic not yet validated: fast_reprompt p=0.71 n=34, tool_fail p=0.83 n=40, …".

### 01 Overview (exec)

| # | Widget | Question | Chart | Metric definition | Drill | Empty / low data |
|---|---|---|---|---|---|---|
| 1.0 | Data coverage strip | How much of the org do these numbers reach? | One-line strip above the KPI row, 3 mono values | `telemetry_seats = COUNT(DISTINCT person_id with ≥ 1 event in the 28d) / config.seats_purchased` (falls back to `/ COUNT(people WHERE active)` when seats are unset); `id_email = COUNTIF(id_source='email') / COUNT(*)` over events (shown only when < 99%: people keyed by account fallback may split from their email identity); `text_opt_in = COUNT(DISTINCT person_id in T_text) / COUNT(DISTINCT person_id in T)`; `gate` = one dot per signal (validated `--primary` / beta `--warn`) plus **`gate ETA <date>`** = `MAX(heuristic_gate.planned_label_date)` over unvalidated signals (`ETA not planned` in `--warn` when any is NULL; the date turns `--bad` once it has passed) | `def` drawer → `heuristic_gate` table and per-signal precision | "No telemetry received yet" + setup doc link |
| 1.1 | Weekly active users | Is it adopted? | KPI tile + 12-week sparkline | `WAU = COUNT(DISTINCT person_id)` with ≥ 1 turn in the ISO week (a person on CLI and desktop counts once). Tile = last full week, delta vs prior week | 1.3 | "No telemetry received yet" + setup doc link (§4.5) |
| 1.2 | Penetration | What share of the team uses it? | KPI tile (%) | `WAU / COUNT(people WHERE active AND start_date <= week_end)` | 1.3 | **needs: people table** when `people` is empty |
| 1.3 | Adoption by squad | Which squads lag? | Horizontal bar per squad. Value = penetration; label = WAU/headcount | 1.2 grouped by `display_squad` (§8.2) | `/squad/<s>` (not for merged rows) | A squad with 0 WAU shows an empty bar, not a hidden one |
| 1.4 | Depth of use | Habitual or occasional? | Histogram: people by active days in the 28 days ending `to` (buckets 1, 2–5, 6–12, 13+) | `active_days = COUNT(DISTINCT local date of turn start)` per person | `/squad/<s>?active_days=<bucket>` (§2.3; exec: drawer split only) | < 3 people: low data |
| 1.4b | Feature reach | Agent depth, or only chat? | 3 small bars, % of active people | `uses_mcp` = ≥ 1 `tool_result` with `tool_name LIKE 'mcp\_\_%'`; `uses_auto` = ≥ 1 `permission_mode_changed` with `to_mode='auto'`; `uses_resume` = ≥ 1 `claude_code.session.count` point with `start_type='resume'`. Each: `COUNT(DISTINCT people with flag) / COUNT(DISTINCT active people)` | `/squad/<s>?missing=<flag>` | < 3 active people: low data |
| 1.5 | Clean-turn rate `beta` | Does the AI do what people asked? | KPI tile + weekly line | `1 − COUNTIF(is_friction_b) / COUNT(T_eval)`. Subtitle: "behavioural signals; corrections not included (text-dependent); turns in progress excluded". The `beta` tooltip repeats the 1.0 gate ETA | 2.3 via `/squad/<s>` per squad in the weekly line's tooltip; tile → 02 for managers, drawer split by `display_squad` for exec | low-data rule |
| 1.6 | Notional cost per active person | What does one user cost? | KPI tile (USD/week) | `SUM(cost_usd over A∪X in the last full ISO week, of the people counted in WAU) / WAU`. Same active-person definition as 1.7 (≥ 1 turn). Drawer states the numerator scope: "agent + overhead calls of active people; $<x> of overhead from people with no turn that week is excluded". Subtitle on seat plans: "API-equivalent, not billed; seat = $<seat_usd_month>/month" | 1.8 | — |
| 1.7 | Seat leverage (Claude Code only, lower bound) | What is the Claude Code share of a seat worth at API prices? | Bullet chart: org row + one row per `display_squad`; marker = leverage, reference line at 1.0 | For month `m`: `active_people_m = COUNT(DISTINCT person_id with ≥ 1 turn in m)`; `leverage = SUM(cost_usd of A∪X in m, of those people) / active_people_m / config.seat_usd_month`. Tile caption: "Claude Code only. The seat also covers claude.ai chat and Cowork, not measured here, so real leverage is ≥ this value" | `/squad/<s>` (managers: person rows show a band) | Hidden when `plan_type='api'`; the tile shows real monthly spend instead |
| 1.8 | Where spend goes | Where is spend wasted? | One 100% stacked bar + USD per segment: overhead, cache-cold excess, **cost in friction turns (≤)**, useful. The overhead label splits `disablable` (`prompt_suggestion`) / `fixed` (`generate_session_title`, `auxiliary`, unknown values). Palette fixed in §7.1 | Exclusive allocation per API call (§4.2 `tvf_cost_alloc`): (1) `X` call → overhead (`overhead_kind` = disablable/fixed); (2) `A` call with `is_cold` → `cold_excess = GREATEST(cost − ref_cost(model), 0)`; (3) remainder of `A` calls in turns with `is_friction_b IS TRUE` → friction; (4) rest → useful (turns still open land here until they close; the drawer shows their cost). The 4 sum exactly to total cost. The friction segment is `beta` with 1.5. On seat plans the caption reads "API-equivalent, not billed: read as rate-limit headroom and latency" | segment → overhead: drawer split by `query_source` (R8 card in v1.1); cold: `/insights?rule=R7`; friction: `/turns?flag=friction` | < 20 agent calls: low data |
| 1.9 | Top 3 actions | What do I do this month? | Ranked list (top 3 open insights by impact, org/squad scope only) | §6 | `/turns?insight_key=<k>` or `/sessions?insight_key=<k>` (per rule grain, §6); exec sees the card, the list drill is locked | "No actionable patterns yet (needs ≥ 14 days of data)" |
| 1.10 | Outcomes | Did delivery improve? | Slot card | **needs: GitHub** (PR cycle time, PRs/active dev), **needs: Jira** (lead time). `pull_request.count` / `commit.count` shown if ever received | — | Empty slot with a "connect GitHub" CTA |
| 1.11 | Measured change after actions (before/after, not causal) | What changed after the actions we took? | **v1: slot card.** Text: "Appears 14 days after the first action is marked done" + `done actions: k` + `first measurable: <MIN(done_at) + 14d>`. **v1.1:** KPI tile, 3 lines + "k of n done actions measured". `plan_type='seat'`: line 1 friction turns/month, line 2 tool-wait hours/month, line 3 "USD API-equivalent, not billed". `plan_type='api'`: USD/month first | v1.1: sum of 7.2 deltas over insights with `status='done'` and `done_at ≤ today − 14d`, normalised to 30 days, after attribution (`tvf_insight_attribution`: each turn/call counts in at most one insight). Net figure (negative deltas included) | v1: `/insights?status=done`; v1.1: → 7.2 | "No actions marked done yet" |
| 1.12 | Seats with no Claude Code activity | How many seats show no Claude Code use? | KPI tile: count + share of seats | `no_cc = GREATEST(config.seats_purchased − active_people_m, 0)`. Caption: "May still be used in claude.ai chat or Cowork, which this telemetry does not see. Check before reallocating." No USD figure. When `claude_ai_usage` is joined (slot), the tile adds "no activity on any surface" and its seat cost | `/squad/<s>?status=not_activated` (managers) | **needs: config.seats_purchased**; **needs: claude.ai usage export** for the any-surface figure; hidden when `plan_type='api'` |
| 1.14 | Adoption funnel | Where do people drop out between seat and deep use? | Horizontal funnel, 6 bars; each shows count, % of seats and % of the previous step | 28 days ending `to`, each step is the previous step **AND** its condition, so bars never grow: (1) seats = `config.seats_purchased` (fallback active `people`); (2) telemetry seen = `person_id` with ≥ 1 event; (3) activated = ≥ 1 turn; (4) weekly active = ≥ 1 turn in the last full ISO week; (5) habitual = `active_days ≥ 13`; (6) deep = `uses_mcp OR uses_auto`. Step 2 counts only people matched in `v_person` with `active` (seat holders), unmatched senders are listed in the drawer | step → `/squad/<s>?funnel=<step>` (manager: own squad; admin: pick squad; exec: drawer split by `display_squad`) | No seats configured: funnel starts at step 2 with "needs: config.seats_purchased"; < `k_anon_min` people: low data |
| 1.15 | Output proxy line | What did it produce? (context, not a KPI) | One `--muted` text line under the KPI row, no tile, no trend arrow | `edit acceptance = SUM(code_edit_tool.decision value WHERE decision='accept') / SUM(value)`; `lines = SUM(lines_of_code.count) by type (added/removed)`, over the 28 days. Label: "output proxy, not productivity" | drawer only | Hidden below `k_anon_min` active people; "no edits" when 0 |
| 1.4c (v1.1) | Time to first use | How fast do new joiners start? | KPI (median days) + joiners table (managers/admins) | per person with `start_date` in the last 180 days: `DATE_DIFF(first turn date, start_date, DAY)`; NULL = not activated | row → `/person/<id>` | **needs: people.start_date** |
| 1.13 (v1.1) | Self-reported time saved | The only route to an hours figure | Slot card | `survey_responses`, aggregated, `n ≥ k_anon_min` per cell | — | **needs: survey** |

Cut as vanity: total prompts, total tokens, and total lines of code as headline numbers. Lines appear only in the 1.15 context line and on drill pages. 1.2, 1.4 and 1.4b stay as the detail behind 1.14.

### 02 Squad (manager; exec sees 2.1, 2.3, 2.4, 2.6 when the squad has ≥ k people, never 2.2)

Accepted params: `active_days`, `missing`, `status`, `funnel` (filter 2.2).

| # | Widget | Question | Chart | Metric definition | Drill | Empty / low data |
|---|---|---|---|---|---|---|
| 2.1 | Squad KPI row | Health at a glance | 4 tiles: WAU/headcount, clean-turn rate `beta`, notional cost/active person/week, edit acceptance | Edit acceptance = `SUM(code_edit_tool.decision value WHERE decision='accept') / SUM(value)` (delta points, §4.5) | tile → 2.2 sorted by that column | low-data rule |
| 2.2 | People table | Who needs help? | Table, one row per person in the squad (including people who never used it) | Columns: name, last active date, active days (28d), uses MCP / auto (1.4b flags), text capture (on/off), status badge. **Banded columns** (`low` / `typical` / `high` vs the squad, never numbers): turns, notional cost/week, reject rate, clean-turn rate `beta`, correction rate `beta` (only when the person has ≥ 20 turns with text; else "no text"). Band = below squad P25 / P25–P75 / above P75, computed only when the person has n ≥ 20 closed turns and the squad has ≥ `config.k_anon_min` (5) such people; else "—" (tooltip: "bands need 5 comparable people"). Status: `not activated` = 0 turns and `start_date + 14d < today`; **`may need support`** (see below); `power` = active days ≥ 13; `has seat, no Claude Code activity` = `people.has_seat` and 0 turns in month `m`. Sort: status (not activated, may need support, rest), then name. Never sorted by volume | row → `/person/<id>` | People with no activity are listed with "0", not hidden |
| 2.3 | Friction by category `beta` + coverage chip | Which kinds of work fail? | Horizontal bar per category: full friction rate over `T_text`; bar label n | `COUNTIF(is_friction) / COUNT(*)` over `T_text` (closed turns only) grouped by `category` | `/turns?squad=<s>&category=<c>&flag=friction` | category with n < 20: low data; coverage rule |
| 2.4 | Friction mix | Why do turns fail? | Stacked weekly bars, 5 flags (palette fixed in §7.1); axis "flags", not "turns" | Counts of each flag over `T_eval`. `correction` is counted over `T_text` only and its legend entry shows the coverage chip | `/turns?squad=<s>&flag=<flag>&week=<w>` | — |
| 2.6 | Squad trend | Getting better? | Lines over 12 weeks: weekly clean-turn rate `beta` and WAU | per ISO week | point → same page, that week | < 3 weeks: table instead of line |

**`may need support`** (coaching label, never a rating):
- Hidden entirely (column shows "—", tooltip "available once behavioural signals are validated") until `fast_reprompt`, `tool_fail` and `abandoned` all pass the gate.
- Then set when, in **at least 2 of the last 4 complete ISO weeks**, the person has n ≥ 20 closed turns in that week **and** their weekly `is_friction_b` rate ≥ the squad's weekly median + 15 pp. One bad week cannot set it.
- Shown to the person (3.8) with the same wording and the weeks that triggered it.

Deferred to v1.1: 2.5 model × category heatmap.

### 03 Person (self, the person's manager, admin)

Per-widget visibility for managers is in §8.1. Summary: managers see bands and weekly granularity, never exact cost, times of day or the daily calendar.

| # | Widget | Question | Chart | Metric definition | Drill | Empty |
|---|---|---|---|---|---|---|
| 3.1 | Person KPI row | How am I doing vs my squad? | 5 tiles, each with the squad median as a tick: active days, clean-turn rate `beta`, turns/session, median prompt length, notional cost/week | from `tvf_person_day` | — | < 5 turns: "Not enough activity yet" |
| 3.2 | Activity | When do I use it? | Self/admin: 28-day calendar heatmap, value = turns/day. Manager: 4–12 cells "active this ISO week yes/no" | self: `COUNT(T)` per local day; manager: `COUNT(T) > 0` per ISO week | self: `/sessions?person=<id>&day=<d>`; manager: `/sessions?person=<id>&week=<w>` | — |
| 3.3 | Prompt length vs friction `beta` | Do short prompts hurt me? | Bars: clean-turn rate by length bucket (`<80`, `80–300`, `300–1000`, `>1000` chars), person vs squad. Optional toggle "by category" (coverage chip) | `is_friction_b` rate over `T_eval` grouped by `length_bucket` (length is always known) | `/turns?person=<id>&length_bucket=<b>&flag=friction` | bucket n < 10: low data |
| 3.4 | Cache-cold tax | Am I paying to rebuild the cache? | KPI: `cold_share`, plus split "start or resume / idle > 5 min" and `short_session_share` | `cold_share = SUM(cold_excess) / SUM(cost A)` from `tvf_cost_alloc`; split by `cold_reason`; `short_session_share = COUNT(S_complete with n_turns ≤ 2) / COUNT(S_complete)` | `/sessions?person=<id>&sort=turns_asc` | — |
| 3.5 | Sessions | Which sessions went well or badly? | The `/sessions` list component, embedded, filtered to the person (columns per role, §2.2) | `tvf_sessions` | row → `/session/<id>` | — |
| 3.7 | Weekly trend `beta` | Am I improving? | (a) clean-turn rate over 12 ISO weeks, person solid vs squad median dashed. (b) for the person's top 3 categories: median `prompt_length` **paired with** the clean rate in that category per week (two lines on a shared x-axis) | (a) `1 − COUNTIF(is_friction_b)/COUNT(*)` over `T_eval` per week; (b) over `T_text`: `APPROX_QUANTILES(prompt_length, 2)[OFFSET(1)]` and `1 − COUNTIF(is_friction)/COUNT(*)` per week × category. Weeks with < 5 turns are gaps. Drawer: "Longer prompts are not better by themselves. Read length together with the clean rate" | point → `/sessions?person=<id>&week=<w>` | < 3 weeks: "Trend appears after 3 active weeks"; (b) without text: "needs: text capture opt-in" |
| 3.8 | What my manager sees | Transparency | The person's own 2.2 row exactly as the manager sees it (bands, badges, the weeks behind `may need support`), plus a "viewed by" list from `access_log` | same query as 2.2, filtered to self | — | — |
| 3.6 (v1.1) | Tool profile | Which tools do I depend on, and which do I reject? | Table per tool_name | calls, failure rate, user rejects, p95 duration | `/turns?person=<id>&tool=<t>` | — |

The page also shows a "text capture: on/off since <date>" line for self, with a link to the opt-in instructions (§8.3).

### 04 Session

| # | Widget | Question | Chart | Metric definition | Drill | Empty |
|---|---|---|---|---|---|---|
| 4.1 | Session header | What happened? | Text row | self/admin: person, surface, version, os, `device_id` (short), start/end time, start_type, permission modes seen, notional cost, cache hit ratio. Manager: date, surface, version, start_type, permission modes, cost band, cache hit ratio | — | — |
| 4.2 | Turn timeline | Where did it go wrong? | One block per turn, colour clean (`--primary`) / friction (`--bad`) / abandoned (`--muted`) / open (`--border` outline, `in progress` chip). Self/admin: width = duration, gaps labelled in seconds. Manager: equal-width blocks in order, no durations or gaps | `tvf_turns` for the session, ordered by `start_ts` | block → `/turn/<prompt_id>` | — |
| 4.5 | Outcome strip (self/admin) | What did it produce? | Text: lines added/removed, edit accept/reject counts | `lines_of_code.count`, `code_edit_tool.decision` for the session | — | "no edits" |
| — | Turns in session | — | the `/turns` list component, `session=<id>` | — | row → `/turn/<id>` | — |
| 4.3 (v1.1) | Cost per turn | Was the first turn the expensive one? | Stacked bar per turn: cold excess / other agent / overhead (self/admin) | `tvf_cost_alloc` per turn | bar → turn | — |
| 4.4 (v1.1) | Context size per call | Is context bloated? | Line of `cache_read + input + cache_creation` tokens per A call, 100k reference | raw `api_request` | — | — |

### 05 Turn

| # | Widget | Question | Chart | Metric definition |
|---|---|---|---|---|
| 5.1 | Prompt | What was asked? | Text block + labels (category, tone, length, heuristic_version, `beta` chips) | text from `raw_text` (self, or admin with a reason; ≤ 30 days). Otherwise "text not captured (no opt-in)" or "text expired, derived fields only". Category/tone show "unknown (no text)" when NULL |
| 5.2 | Event waterfall | What did the agent do? | Rows by `event.sequence`: api_request (model, tokens, ttft, query_source; cost and timestamps self/admin only), tool_decision (accept/reject + source), tool_result (tool, success, duration, sizes), assistant_response (length) | all events with this `prompt.id` |
| 5.3 | Friction flags | Why is it flagged? | Chips: `user_reject`, `tool_fail`, `fast_reprompt` (with its reason: no answer / reject / tool fail / correction cue), `correction_next` `beta`, `abandoned`, `cold` (with `cold_reason`). An `open` turn shows only `in progress` ("flags are evaluated 30 min after the session's last event"). Each chip links to the event that set it; gated flags carry `beta` | flags from `tvf_turns` |
| 5.4 | Response | What did it answer? | Collapsed text block | `raw_text` kind `response`, same rules as 5.1 |
| 5.5 | Next turn | How did the user react? | Link card to the next turn; self/admin: gap seconds; manager: `< 60 s` / `≥ 60 s` | `LEAD()` over the session |

### 06 Health & Governance (manager, admin; exec sees org and k-anon squad aggregates)

| # | Widget | Question | Chart | Metric definition | Drill | Empty |
|---|---|---|---|---|---|---|
| 6.1 | Tool reliability `beta` (tool_fail) | Which tools break? | Table: tool_name, calls, failure rate, p50/p95 duration, mean result size, time in failed calls | `tool_result` grouped by `tool_name`; `failure_rate = COUNTIF(success=false)/COUNT(*)`; `fail_time_s = SUM(duration_ms WHERE success=false)/1000` | `/turns?tool=<t>&flag=tool_fail` | — |
| 6.2a | MCP servers (attributed from tool calls) | Which MCP servers' tools fail or are slow? | Table: server, tools seen, calls, failure rate, p95 duration, time in failed calls, people affected (count for exec/cross-squad) | `tool_result` rows with `mcp_server = REGEXP_EXTRACT(tool_name, r'^mcp__(.+?)__')` not NULL, grouped by server | `/sessions?mcp_server=<m>&flag=tool_fail` | "no MCP tool calls observed" |
| 6.2b | MCP connections (unattributed) | Are MCP connections failing, and how much time do they cost? | KPI row (attempts, failure rate, time lost) + bar by `error_code` + bar by `transport_type` + people affected | `attempts = COUNT(*)`; `failed = COUNTIF(status != 'connected')`; `time_lost_s = SUM(duration_ms WHERE status != 'connected')/1000`. Per-server attribution: **needs: server name attr**. Day 1 check (§4.6) on real CLI and desktop rows: if a name key exists, 6.2a and 6.2b merge into one table before Day 4 | `/sessions?mcp_conn=failed&error_code=<e>` | "no MCP connections observed" |
| 6.3 (v1.1) | API latency and errors | Is the model side slow? | p50/p95 `ttft_ms`/`duration_ms` per day per model; `api_error` count per day; unknown `query_source` values | error breakdown: **needs: observed api_error shape** | day → same page | — |
| 6.4 (v1.1) | Permission posture | Are people auto-approving everything? | Stacked bar per `display_squad`: `tool_decision` by source | `COUNT by source / total` | squad → 02 | — |
| 6.6 (v1.1) | Context baseline | How heavy is our default context? | KPI + bar per `display_squad`: median `cache_read_tokens` of the first A call of each turn | `APPROX_QUANTILES(...)[OFFSET(1)]` | squad → 02 | — |
| 6.8 (v1.1) | Ingest health (admin) | Is the data complete? | Table: rejected points by reason, last event per person, devices per person, events keyed by account fallback (`id_source='account'`), emails missing in `people`, text dropped for non-opted-in senders (count) | `ingest_rejects`, `MAX(event_ts)` and `COUNT(DISTINCT device_id)` per `person_id` | — | "all clients healthy" |
| 6.9 (v1.1) | Model mix by squad | Which tiers is each squad spending on? | 100% stacked bar per `display_squad`: share of agent cost by `tier` (large/medium/small/unknown) | `SUM(cost_usd) by display_squad, tier / SUM(cost_usd) by display_squad` over A, from `v_api_calls.tier` | squad → 02 | "no model_tiers rows" → all `unknown` |

### 07 Insights

| # | Widget | Question | Chart | Metric definition | Drill |
|---|---|---|---|---|---|
| 7.1 | Action list | What should we do? | Card list sorted by impact; each card = rule, scope, evidence numbers, recommended action, estimated impact, `beta` chip if the rule uses a gated signal, coverage chip if it uses text, status (open/done/dismissed). Accepts `?rule=`, `?status=`, `?squad=` | rows of `v_insights` (§6) | `/turns?insight_key=<k>` or `/sessions?insight_key=<k>` (grain per rule, §6) |
| 7.2 (v1.1) | Done tracker | Did anything change after the action? | Before/after mini chart per done insight; delta row feeding 1.11 | For insight `i` with trigger metric `M_i` over its attributed rows: `before` = 14 days before `done_at`; `after` = `done_at` to `min(done_at+28d, today)` (needs ≥ 14 days). Delta per 30 days: USD rules (R1, R3, R7, R8): `(cost_per_unit_before − after) × units_after_per_30d` of the affected component (unit = agent call for R1, cold call for R7, overhead call for R8, turn for R3); turn rules (R4, R5, R6, R12): `(rate_before − rate_after) × turns_after_per_30d`; time rules (R2a, R2b, R11): `(fail_time_per_turn_before − after) × turns_after_per_30d`. Label on every chart: "before/after, not causal — no control group" | `/turns?insight_key=<k>` |

---

## 4. Derived data model (BigQuery `brain003-mvp.darwinloop_telemetry`, `southamerica-east1`)

Dataset options: `max_time_travel_hours = 48` (§8).

### 4.1 Tables

| Table | Grain | Key columns | Partition / retention |
|---|---|---|---|
| `raw_events` | one OTLP log record | `event_ts TIMESTAMP`, `ingest_ts`, `event_name`, `session_id`, `prompt_id`, `event_sequence INT64`, `person_id` (§4.5), `id_source` (`email`/`account`), `device_id` (= `user.id`), `user_email`, `account_uuid`, `org_id`, `service_name`, `service_version`, `os_type`, `host_arch`, `terminal_type`, `team_attr`, `env_attr`, `attrs JSON` (all attributes **minus** `prompt` and `response`), `derived JSON` (`user_prompt` only: `has_text BOOL`, `category`, `tone`, `correction_kw` — the last three NULL when `has_text=false` —, `length_bucket`, `heuristic_version`) | `PARTITION BY DATE(event_ts)`, `CLUSTER BY person_id, session_id`, 400 days |
| `raw_text` | one prompt or response text, **opted-in people only** | `event_ts`, `session_id`, `prompt_id`, `event_sequence`, `person_id`, `user_email`, `kind` (`prompt`/`response`), `text STRING` | `PARTITION BY DATE(event_ts)`, `CLUSTER BY person_id`, **expiration 30 days** |
| `raw_metrics` | one OTLP **delta** data point | `ts`, `start_ts`, `metric_name`, `value FLOAT64`, `person_id`, `device_id`, `user_email`, `session_id`, `service_name`, `attrs JSON` | `PARTITION BY DATE(ts)`, `CLUSTER BY person_id`, 400 days |
| `ingest_rejects` | one rejected batch slice | `ts`, `reason` (`cumulative_temporality`, `bad_token`, `org_mismatch`, `deleted_subject`, `text_not_opted_in`, `no_identity`), `metric_name`, `person_id`, `service_name`, `service_version`, `points INT64` | 90 days. No email, no text |
| `people` | one person | `email` (key; `person_id` is derived from it in `v_person`, never typed by hand), `name`, `squad`, `role` (`exec`/`manager`/`dev`/`admin`), `manager_email`, `squad_lead BOOL`, `start_date`, `active BOOL`, `has_seat BOOL` (optional), **`text_opt_in BOOL` (default false)**, **`text_opt_in_at TIMESTAMP`** | none; CSV load |
| `config` | single row | `plan_type` (`seat`/`api`), `seat_usd_month`, `seats_purchased INT64`, `org_id`, `fast_reprompt_s` (60), `cache_ttl_s` (300), `resume_gap_s` (21600), `followup_window_s` (1800), `open_turn_grace_s` (1800, must be ≥ `followup_window_s`; checked at startup), `min_turns_rate` (20), `k_anon_min` (5) | none |
| `heuristic_gate` | heuristic_version × signal | `heuristic_version`, `signal` (`fast_reprompt`, `tool_fail`, `abandoned`, `correction`, `category`), `n_labelled`, `precision`, `validated BOOL`, `validated_at`, `validated_by`, `planned_label_date DATE` (feeds the 1.0 gate ETA) | none; written by an admin (sign-off) |
| `model_tiers` | one model pattern | `model_pattern` (LIKE), `tier`, `list_usd_per_mtok_input`, `_output`, `_cache_read`, `_cache_write`, `updated_at` | none |
| `heuristic_labels` | one hand-labelled turn × signal | `prompt_id`, `heuristic_version`, `signal`, `fired BOOL`, `true_is_friction BOOL` (for flags) / `true_is_correction BOOL` / `true_category`, `labeller_email`, `labelled_at` | none. No text |
| `insight_status` | one insight | `insight_key`, `status`, `owner_email`, `done_at`, `note` | none |
| `access_log` | one view of a person/session/turn/list | `viewer_email`, `target_person_id`, `level` (`person`/`session`/`turn`/`list`/`text`), `ts`, `reason` | 400 days |
| `deleted_subjects` | one erased person | `person_id`, `account_uuids ARRAY<STRING>` (to also catch account-fallback rows), `requested_at`, `completed_at` | none |
| `survey_responses` (slot) | person × month × category | `email`, `month`, `category`, `minutes_saved_week` | 400 days. **needs: survey** |
| `claude_ai_usage` (slot) | person × month | `email`, `month`, `active_days_chat`, `active_days_cowork` | **needs: claude.ai usage export** (admin console CSV); feeds 1.12 "no activity on any surface" |
| `outcomes_*` (slot) | per PR / issue | **needs: GitHub** (`outcomes_github_pr`: author_email, opened_at, merged_at, additions, deletions), **needs: Jira** (`outcomes_jira_issue`) | out of v1; `LEFT JOIN` when present |

Text lives in its own table because partition expiration deletes whole partitions. Derived fields are computed at ingest so they outlive the text.

**Single cost source:** `api_request.cost_usd` and its token fields feed every cost and token widget. `claude_code.cost.usage` and `claude_code.token.usage` are stored but read by no view. Metrics feed only `session.count` (start_type), `active_time.total`, `lines_of_code.count` and `code_edit_tool.decision`.

### 4.2 Derived views and table-valued functions

Turn- and call-level logic uses window functions (`LEAD`, `ROW_NUMBER`, `LAG`), so an outer date filter would not prune partitions. These are **table-valued functions** with date parameters that filter `raw_events` on `DATE(event_ts)` first:

```sql
CREATE TABLE FUNCTION darwinloop_telemetry.tvf_turns(from_d DATE, to_d DATE) AS (
  WITH ev AS (
    SELECT * FROM darwinloop_telemetry.raw_events
    WHERE DATE(event_ts) BETWEEN DATE_SUB(from_d, INTERVAL 1 DAY) AND DATE_ADD(to_d, INTERVAL 1 DAY)  -- UTC pad: ≥ 21 h look-back and look-ahead around the local window
      AND person_id NOT IN (SELECT person_id FROM darwinloop_telemetry.deleted_subjects)
  ) ...
  SELECT * FROM turns WHERE DATE(start_ts, 'America/Sao_Paulo') BETWEEN from_d AND to_d
);
```

**Window rules (why a turn's flags do not depend on the window it is read in).** The local window `[from_d 00:00, to_d 24:00) America/Sao_Paulo` = `[from_d 03:00Z, to_d+1 03:00Z)`. The UTC-date pad loads from `from_d−1 00:00Z` to `to_d+2 00:00Z`, so every in-window event has **≥ 27 h of look-back and ≥ 21 h of look-ahead**. Every window-sensitive rule uses a fixed threshold shorter than that:
- cold call: previous agent call in the session within `cache_ttl_s` (300 s); cold reason: previous agent call within `resume_gap_s` (6 h);
- fast re-prompt: next prompt within `fast_reprompt_s` (60 s); abandonment and next-turn correction: next prompt within `followup_window_s` (30 min).
So "no previous/next event in the load" always means "none within the threshold", and `call_rank = 1` is never used. Test (Day 2, seeded fixture with sessions crossing midnight, a resume after 30 h and a turn at 23:59 local): for each day `d`, the flags, `is_cold` and `cold_reason` of every turn on `d` are identical in `tvf_turns(d, d)` and `tvf_turns(d−7, d+7)`.

Same pattern: `tvf_api_calls`, `tvf_cost_alloc`, `tvf_sessions`, `tvf_person_day`, `tvf_insights` (v1.1: `tvf_insight_attribution`). Small lookups stay plain views (`v_person`, `v_squad_k`, `v_heuristic_quality`). shortcut: TVFs recompute per request; upgrade to scheduled `MERGE` into tables when `raw_events` passes ~10 GB or page load exceeds 3 s.

**`v_person`** (grain: `person_id`): `people` (with `person_id = TO_HEX(SHA256(LOWER(TRIM(email))))`, the same function as the ingest) FULL JOIN the distinct `person_id`s seen in `raw_events`. Columns add `n_devices = COUNT(DISTINCT device_id)`, `surfaces ARRAY`. `squad = COALESCE(people.squad, team_attr, 'unassigned')`. Emails missing from `people` get squad `unassigned`, role `dev`, `text_opt_in=false`.

**`tvf_api_calls`**: `api_request` rows unpacked (`model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, cost_usd, duration_ms, ttft_ms, query_source, effort`). Adds:
- `is_agent = query_source IN ('sdk','main')`
- `prev_agent_gap_s = TIMESTAMP_DIFF(event_ts, LAG(event_ts) OVER (PARTITION BY session_id, is_agent ORDER BY event_ts, event_sequence), SECOND)`, over the padded load
- `is_cold = is_agent AND (prev_agent_gap_s IS NULL OR prev_agent_gap_s > config.cache_ttl_s)`. NULL is safe to read as cold: the load reaches ≥ 27 h back, far beyond the ~5 min cache TTL
- `cold_reason = IF(prev_agent_gap_s IS NOT NULL AND prev_agent_gap_s <= config.resume_gap_s, 'idle_gap', 'start_or_resume')`: start or resume = no agent call in the session for 6 h (a new session, or a `--resume` of an old one); idle gap = a pause of 5 min to 6 h inside a working session
- `overhead_kind = CASE WHEN is_agent THEN NULL WHEN query_source = 'prompt_suggestion' THEN 'disablable' ELSE 'fixed' END`
- `turn_call_rank` (partitioned by `prompt_id`), `tier` via `model_tiers`.

**`tvf_turns`** (grain: `prompt_id`)

| Column | Definition |
|---|---|
| `start_ts`, `end_ts` | `event_ts` of `user_prompt`; `MAX(event_ts)` over the turn's events |
| `person_id`, `device_id`, `session_last_ts` | `session_last_ts = MAX(event_ts) OVER (PARTITION BY session_id)` in the load |
| `turn_state` | `'open'` when the turn has no next turn in its session **and** `TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), session_last_ts, SECOND) < config.open_turn_grace_s`; else `'closed'`. A turn can be open only while its session was active in the last 30 min, so historic windows have none |
| `prompt_length`, `length_bucket` | always present |
| `has_text`, `category`, `tone`, `correction_kw`, `heuristic_version` | from `derived`; NULL category/tone/correction when `has_text=false` |
| `n_agent_calls`, `agent_cost`, `overhead_cost`, tokens by type, `has_cold` | from `tvf_api_calls` |
| `main_model` | model with the largest agent cost in the turn |
| `n_tool_calls`, `n_tool_fail`, `fail_time_ms` | `tool_result` count, `COUNTIF(success=false)`, `SUM(duration_ms WHERE success=false)` |
| `n_user_reject` | `tool_decision WHERE source='user_reject'` (or `decision='reject' AND source != 'config'`) |
| `has_response` | any `assistant_response` with `query_source IN ('sdk','main')` or no query_source |
| `next_gap_s` | `TIMESTAMP_DIFF(LEAD(start_ts) OVER (PARTITION BY session_id ORDER BY start_ts), end_ts, SECOND)` |
| `next_has_text`, `next_correction_kw` | `LEAD(has_text)`, `LEAD(correction_kw)`, kept only when `next_gap_s <= config.followup_window_s` (else NULL: a correction typed hours later is not a reaction to this turn) |
| all `flag_*`, `is_friction_b`, `is_friction` | NULL when `turn_state = 'open'`; the definitions below apply to closed turns |
| `flag_user_reject` | `n_user_reject > 0` |
| `flag_tool_fail` | `n_tool_fail > 0` (v1; tuning note below) |
| `flag_fast_reprompt` | `next_gap_s < config.fast_reprompt_s AND (NOT has_response OR flag_user_reject OR flag_tool_fail OR next_correction_kw IS TRUE)` |
| `fast_reprompt_reason` | first of `no_answer`, `reject`, `tool_fail`, `correction_cue` that holds |
| `flag_abandoned` | `NOT has_response AND (next_gap_s IS NULL OR next_gap_s > config.followup_window_s)`: no answer, and the person did not continue the session within 30 min. Window-stable because the look-ahead is ≥ 21 h |
| `is_friction_b` | `flag_user_reject OR flag_tool_fail OR flag_fast_reprompt OR flag_abandoned` |
| `is_friction` | `is_friction_b OR next_correction_kw IS TRUE` (= `is_friction_b` when `next_has_text` is not true) |

Note: a fast follow-up after a normal answer ("ok, now run the tests") is **not** flagged. The flag adds signal over the other flags only for interrupted turns (no answer, user typed again within 60 s) and for correction cues; it is kept as its own flag so the gate can measure it.

Rates (canonical): clean-turn rate `1 − COUNTIF(is_friction_b)/COUNT(*)` over `T_eval`. Correction rate `COUNTIF(next_correction_kw)/COUNTIF(next_has_text)`. Reject rate `COUNTIF(flag_user_reject)/COUNT(*)` over `T_eval`. Category friction rate over `T_text`.

Tuning note: `n_tool_fail > 0` will over-flag when the agent recovers from a failed grep. If labelled tool-fail-only turns are judged clean in more than half of cases, the flag becomes "a failure with no later success of the same tool in the turn" (`heuristic_version` bump).

**`tvf_cost_alloc`** (grain: one `api_request`; exclusive waste allocation)

```sql
ref AS (SELECT model, APPROX_QUANTILES(cost_usd, 2)[OFFSET(1)] AS ref_cost
        FROM tvf_api_calls(from_d, to_d) WHERE is_agent AND NOT is_cold GROUP BY model)
SELECT c.*,
  IF(NOT c.is_agent, c.cost_usd, 0)                                                 AS overhead,
  IF(c.is_cold, GREATEST(c.cost_usd - IFNULL(r.ref_cost, c.cost_usd), 0), 0)        AS cold_excess,
  IF(c.is_agent AND t.is_friction_b IS TRUE, c.cost_usd - <cold_excess>, 0)         AS friction,  -- open turns → useful
  c.cost_usd - <overhead> - <cold_excess> - <friction>                              AS useful
FROM tvf_api_calls(from_d, to_d) c LEFT JOIN tvf_turns(from_d, to_d) t USING (prompt_id) LEFT JOIN ref r USING (model)
```

Each call's cost lands in exactly one ordered bucket, so segments sum to the total. Test: `ABS(SUM(overhead+cold_excess+friction+useful) − SUM(cost_usd)) < 1e-9`.

**`tvf_sessions`** (grain: `session_id`, sessions with ≥ 1 turn in the window): `person_id`, `device_id`, surface, version, `start_ts`, `end_ts`, `n_turns`, `n_friction_b`, `agent_cost`, `overhead_cost`, `cold_excess`, `cache_hit = cache_read/(cache_read+input+cache_creation)`, `active_s`, `start_type`, `lines_added/removed`, `edits_accept/reject`, `models ARRAY`, `n_tool_fail`, `n_mcp_conn_fail`, `is_live` (last event < `open_turn_grace_s` ago), `is_complete` (every loaded event of the session is inside the local window). Per-session shape metrics (turns/session, `short_session_share`, 4.2 timeline gaps) use only `is_complete` sessions; counts and sums use all. shortcut: a session idle > 27 h before the window then continued inside it looks complete; rare, accept until the TVFs become scheduled tables.

**`tvf_person_day`** (grain: `person_id` × local day; one row even when the person used CLI and desktop on two devices): squad, surface, sessions, turns, turns with text, friction turns (`_b` and full over text), rejects, corrections, abandoned, agent/overhead/cold-excess cost, tokens by type, median prompt length, active seconds, lines +/−, edit accept/reject, `uses_mcp`, `uses_auto`, `uses_resume`. Every page KPI aggregates from here, except per-turn distributions.

**`v_tool_health`** / **`v_mcp_conn`**: as in v2 (day × tool × squad; day × `person_id` × status × transport × error_code; no server column on connections).

**`v_squad_k`**: squad, `active_headcount`, `display_squad = IF(active_headcount >= k_anon_min, squad, 'other')`.

**`v_heuristic_quality`**: `heuristic_labels` ⋈ `tvf_turns` on `prompt_id` and `heuristic_version`. Per signal: `n_labelled`, `precision = COUNTIF(fired AND truth) / COUNTIF(fired)`, `recall`, and for `category` the accuracy and confusion matrix.

**`tvf_insights`**: `UNION ALL` of the rule queries in §6. Each emits `insight_key, rule, scope_type, scope_id, evidence JSON, action, impact_usd_month, impact_turns_month, impact_seconds_month, uses_gated BOOL, uses_text BOOL`. **`v_insight_evidence`** (`insight_key, prompt_id, session_id`) comes from the same rule queries and backs `?insight_key=`.

**`tvf_insight_attribution`** (v1.1; de-duplication for 1.11/7.2): for every agent call / turn in the after and before windows, list the done insights whose scope contains it and whose rule touches that component; keep one with `ROW_NUMBER() OVER (PARTITION BY call_or_turn_id ORDER BY scope_specificity DESC /* person 3 > squad 2 > org 1 */, done_at ASC, insight_key) = 1`. Each 7.2 delta is computed only over its attributed rows, so a turn or call counts in at most one insight's delta.

### 4.3 Heuristics (v1, `heuristic_version = 'kw-3'`)

One Python function at ingest, run **only when the text is kept** (person opted in, §4.5). The prompt is lowercased and NFC-normalised; all regexes use Python `re` on `str` (Unicode-aware `\b`). Unit-tested with a fixture of ≥ 40 labelled PT/EN prompts including the known false positives: `não altere X`, `precisa`, `decisão`, `escrever`, `crítico`, `específico`, `address`, `docker`, `no caso`, `ainda não existe`. Without text the function returns `has_text=false` and NULLs, plus `length_bucket` from `prompt_length`.

**Fast re-prompt:** next `user_prompt` in the same session < `config.fast_reprompt_s` (60 s) after the turn's last event **and** the turn had no answer, a reject or a tool failure, or the next prompt carries a correction cue (§4.2).

**Abandonment:** no agent answer and no next prompt in the session within `followup_window_s` (30 min); evaluated only once the turn is closed (session silent for `open_turn_grace_s`).

**Auxiliary exclusion:** `api_request` with `query_source NOT IN ('sdk','main')` (observed: `prompt_suggestion`, `generate_session_title`, `auxiliary`) is overhead: excluded from model mix, context baseline, cold cost and per-turn quality; its own 1.8 segment. `prompt_suggestion` is `disablable` (users can turn suggestions off); `generate_session_title`, `auxiliary` and unknown future values are `fixed` and never count toward R8. Unknown values default to fixed overhead. Same for `assistant_response` with a `query_source`.

**Category (first match wins; word-boundary regex, `re.I`):**

| Priority | Category | Regex |
|---|---|---|
| 1 | `bugfix` | `\b(fix(es|ed|ing)?|bugs?|erros?|errors?|quebr\w*|falh\w*|traceback|exceptions?|stack ?trace|broken|crash\w*)\b`, `\bnão (está )?funciona\w*`, `\bdoesn'?t work\b` |
| 2 | `test` | `\b(tests?|testes?|testar|testing|pytest|jest|vitest|coverage|cobertura|specs?|unit ?tests?)\b` |
| 3 | `refactor` | `\b(refactor\w*|refator\w*|simplif\w*|clean ?up|limpa[r]?|renome\w*|rename\w*|extract\w*|extrai[r]?)\b` |
| 4 | `review` | `\b(review\w*|revis[aeã]\w*|code ?review|audit\w*)\b` |
| 5 | `ops` | `\b(commit\w*|push|merge\w*|deploy\w*|docker\w*|git|prs?|pull request|ci|cd|pipelines?|gcloud|terraform|kubectl|helm)\b` |
| 6 | `docs` | `\b(readme|docs?|documenta\w*|document(ation)?|changelog|docstrings?|coment[aá]rios?|comments?)\b` |
| 7 | `feature` | `\b(add|adicion\w*|implement\w*|cri[ae]r?|criei|create|build|nov[ao]s?|new|feature)\b` |
| 8 | `question` | ends with `?`, or `^(como|o que|por ?que|qual|quais|why|what|how|explain|explica\w*)\b` |
| 9 | `other` | text present, nothing matched (distinct from NULL = no text, shown as `unknown`) |

**Correction cue (`correction_kw`)**, first 5 tokens only:

| Pattern | Why it is safe |
|---|---|
| `^(não|nao|no|nope)\s*[,.!;:]` | bare negation only when punctuation follows; `não altere X` does not match |
| `\b(não|nao) (é|era|foi) (isso|assim)\b`, `\bisso não\b`, `\bnot (that|this|what)\b`, `\bthat'?s not\b` | explicit rejection |
| `\b(errad[oa]|wrong|incorret[oa]|incorrect)\b` | — |
| `\b(de novo|again|outra vez)\b`, `\bainda (não|nao|está|esta|dá|da|continua)\b`, `\bstill (not|broken|failing|wrong)\b`, `\bcontinua (dando|com|quebr\w*|falh\w*)\b` | `ainda`/`still` only with a failure word |
| `\b(na verdade|actually|instead|em vez|ao invés)\b` | redirection |
| `\b(desfa[zç]\w*|undo|revert\w*|volta[r]? (atrás|o que))\b` | rollback |

**Other tones (display only, never in KPIs):** `frustration` = `!!`+, or ≥ 50% uppercase with length ≥ 10, or a short profanity list in code. `positive` = `\b(obrigad[oa]|valeu|thanks?|perfeito|perfect|ótimo|great|boa)\b`. Else `neutral`.

**Validation gate (per signal):**

1. Sampling: `scripts/sample_for_labels.py` draws, per signal, 40 turns where it fired and 20 where it did not, stratified by squad. Behavioural signals (`fast_reprompt`, `tool_fail`, `abandoned`) sample from **all** people and are labelled from derived fields (05 waterfall, next-turn gap) — no text needed. Text signals (`correction`, `category`) sample only opted-in people; the admin pulls text with access reason `heuristic-validation`, logged.
2. The labeller fills `true_is_friction` (behavioural flags), `true_is_correction`, `true_category` in a CSV, loaded into `heuristic_labels` (no text).
3. `v_heuristic_quality` computes precision per signal. When `n_labelled ≥ 30` fired cases and `precision ≥ 0.8`, an admin writes a `heuristic_gate` row with `validated=true`. Deliberate human sign-off.
4. While a signal is not validated, or after any `heuristic_version` change, every number using it carries `beta` (§3 gate rule), insights with `uses_gated` rank below the others, and `may need support` stays hidden. If a signal stays under 0.8 after tuning, it is dropped from `is_friction_b` with a version bump.

When the LLM judge (`lib/detection/classify_feedback`) lands, it writes `heuristic_version='llm-1'` and passes the same gate. It also only sees opted-in text.

### 4.4 Squad attribution

`squad = COALESCE(people.squad, team_attr, 'unassigned')`. `OTEL_RESOURCE_ATTRIBUTES=team=<squad>` is a fallback for people missing from `people`.

### 4.5 Ingest and hosting

Two Cloud Run services from **one image**, region `southamerica-east1`, `APP_ROLE` selects routes:

| Service | `APP_ROLE` | Access | Routes |
|---|---|---|---|
| `darwinloop-ingest` | `ingest` | `--allow-unauthenticated`; the app checks `Authorization: Bearer <token>` against Secret Manager `darwinloop-ingest-token` (constant-time; 401 otherwise) and rejects `organization.id != config.org_id` | `POST /v1/logs`, `POST /v1/metrics` (OTLP/HTTP JSON) |
| `darwinloop-dashboard` | `dashboard` | IAP, Workspace domain only; app verifies the IAP JWT (`X-Goog-IAP-JWT-Assertion`) and reads the email | `GET /`, page routes, `/api/<widget>`, `/api/list/*`, admin routes |

Deviates from context.md's "one service" on purpose: IAP covers a whole service and OTLP exporters cannot do Google sign-in. Service accounts: ingest has `bigquery.dataEditor` on raw tables and read on `people`/`config`/`deleted_subjects`; dashboard has `dataViewer` + `jobUser`, write only to `insight_status` and `access_log`. shortcut: one shared org token means identity is asserted by the client; upgrade to per-person tokens if spoofing becomes a concern.

**Identity at ingest.** For every record: `person_id = hex(sha256(email.strip().lower()))` when `user.email` is present (`id_source='email'`), else `hex(sha256('acct:' + user.account_uuid))` (`id_source='account'`); a record with neither is rejected (`ingest_rejects.reason='no_identity'`). `user.id` is stored as `device_id` only. The same function is used in `v_person` (SQL) and has a unit test that both produce the same hex for mixed-case, padded emails. Day 1 checks the share of `id_source='account'` on real CLI and desktop payloads (expected ≈ 0, since both surfaces send `user.email`).

**Managed settings `env`** (for everyone; **no** prompt logging here):

```
CLAUDE_CODE_ENABLE_TELEMETRY=1
OTEL_LOGS_EXPORTER=otlp
OTEL_METRICS_EXPORTER=otlp
OTEL_EXPORTER_OTLP_PROTOCOL=http/json
OTEL_EXPORTER_OTLP_ENDPOINT=https://<darwinloop-ingest URL>
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer <token>
OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta     # required
OTEL_RESOURCE_ATTRIBUTES=team=<squad>                        # optional fallback
```

**Per-person text opt-in** (both steps required):
1. The person asks for it in writing (form); an admin sets `people.text_opt_in=true`, `text_opt_in_at=now()`.
2. The person adds `"env": {"OTEL_LOG_USER_PROMPTS": "1"}` to their own user `~/.claude/settings.json`.

**Text gate at ingest:** the ingest keeps an in-memory set of opted-in emails, refreshed from `people` every 5 minutes (on load failure: empty set, i.e. fail closed). For `user_prompt` and `assistant_response` records: if `user.email` is opted in, `prompt`/`response` go to `raw_text` and heuristics run; otherwise the text attributes are deleted **before any processing**, derived fields are NULL with `has_text=false`, and one `ingest_rejects(reason='text_not_opted_in')` count is written (no text). `assistant_response.response` follows the same rule because it can contain client code and data. In every case the text is removed from `attrs` before the `raw_events` insert.

**Metric temporality:** DELTA points and gauges → `raw_metrics`. CUMULATIVE points are not stored: counted into `ingest_rejects(reason='cumulative_temporality')`, response HTTP 200 with OTLP `partialSuccess.rejectedDataPoints` and a message naming the env var.

**Writes:** `insert_rows_json` (streaming), batched per table. Rows stay in the streaming buffer up to ~90 minutes (matters for deletion, §8). Records from `deleted_subjects` are dropped and counted.

### 4.6 Build plan (one engineer, 6 working days)

v3 claimed 5 days with insight attribution and the role matrix squeezed in; that was not honest. v4 drops the SQL that has no data at launch and gives access control its own day.

- **Day 1:** image with both roles; ingest (auth, `person_id`, temporality, text gate, heuristics kw-3 + fixture tests); raw tables; `deploy.sh` (both services, secret, IAP, service accounts). **Payload checks on real CLI and desktop rows** (each result written into this spec): (a) does `mcp_server_connection` carry a server name? yes → merge 6.2a/6.2b; (b) share of events without `user.email`; (c) the exact settings key that disables prompt suggestions (for R8's v1.1 action text; until verified the card says "needs: verified settings key"); (d) `api_error` shape.
- **Day 2:** TVFs and views (`tvf_api_calls`, `tvf_turns` with `turn_state`, `tvf_cost_alloc` with the sum assertion, `tvf_sessions`, `tvf_person_day`, `v_person`, `v_squad_k`, `v_tool_health`, `v_mcp_conn`, `v_heuristic_quality`); seed script with synthetic events covering every flag, an open turn, two devices for one email, and the window-stability test (§4.2).
- **Day 3:** API layer (parametrised SQL, `{rows, sql, n, coverage, gate}` shape) + list views + 01 (incl. 1.14 funnel, 1.15 line, 1.11 slot) + 02.
- **Day 4:** 03, 04 (4.1, 4.2, 4.5), 05, 06 (6.1, 6.2a, 6.2b).
- **Day 5 — access control only:** role resolution from IAP email; manager projections per widget (§8.1 matrix) enforced server-side; 403s (`day=`, `cost_desc`, out-of-scope person); `access_log` writes and the 3.8 "viewed by" list; `v_squad_k` / `display_squad` on every squad split (§8.2); bands with the `k_anon_min` minimum; one API test per role × page using fixture users (dev, manager, squad_lead, exec, admin).
- **Day 6:** insights R1, R2a, R2b, R4, R7, R9 + `v_insight_evidence` + 7.1 + 1.9; empty/low-data states; mobile pass; team notice and opt-in form text.
- If only 5 days are available, Day 6 slips: 1.9 and 07 show the empty state at launch and everything else ships. Access control is never the part that slips.
- **v1.1:** 1.11 live, 7.2, `tvf_insight_attribution`, R5, R8, 1.4c, 1.13, 3.6, 4.3, 4.4, 6.3, 6.4, 6.6, 6.8, 6.9, R3, R6, R10–R12, 2.5, survey and claude.ai usage loaders, self-serve opt-in toggle.

Stack: Python (FastAPI) + `google-cloud-bigquery`; static HTML + vanilla JS + one chart library pinned from cdnjs. No Supabase.

---

## 5. Value / ROI (honest framing)

1. **Notional cost, never "savings" without a comparison.** `cost_usd` is the client's API-price estimate. With `plan_type='seat'`, every USD widget says "API-equivalent, not billed", and money actually paid is `seats_purchased × seat_usd_month`. With `plan_type='api'`, the same numbers are real spend.
2. **Seat leverage (1.7)** is "Claude Code only, lower bound": `SUM(cost_usd of A∪X in m, of active people) / active_people_m / seat_usd_month`, with people counted by `person_id` (one per human, not per device). The seat also buys claude.ai chat and Cowork, which this telemetry does not see, so real leverage is at least this value. High = heavy users; very low = people to enable.
3. **Seats with no Claude Code activity (1.12)** is a count, not money. A seat with no Claude Code use may be fully used in chat or Cowork. Only after joining `claude_ai_usage` (**needs: claude.ai usage export**) can a seat be called idle on every surface, and only then is its cost shown.
4. **Where spend goes (1.8)** is an exclusive allocation and always an upper bound (≤). "Cost in friction turns" is spend in turns that showed friction, not spend proven wasted. On seat plans it reads as rate-limit headroom and latency. Only the `disablable` part of overhead is an action lever; the `fixed` part is the cost of using the product. Time lost (tool failures, MCP connects) is real on any plan.
5. **Measured change after actions (1.11/7.2, v1.1; v1 shows a dated slot)** is a before/after comparison, not causal (no control group, seasonality and team changes are not removed). Each turn or call counts in at most one action. On seat plans the headline is friction turns and tool-wait hours; USD is secondary and "API-equivalent, not billed". Net figure, including actions that made things worse.
6. **Prompt-quality improvement** is a trend, not a score: 3.7 per person, 2.6 per squad. Prompt length is always read together with the clean rate.
7. **Output proxies, labelled as proxies:** edit acceptance, lines added/removed, active time. Context only, never productivity scores or rankings; hidden from managers at session level.
8. **Hours saved:** no telemetry figure. The only paths are 1.13 (**needs: survey**, self-reported, n ≥ k_anon_min) or **needs: GitHub/Jira** outcomes.
9. **Outcome slot (1.10):** `outcomes_github_pr` joined on author email → PR cycle time and PRs per active dev, split by "AI-heavy week" (person above the squad median of active days) vs not. `outcomes_jira_issue` → lead time by squad. Views already `LEFT JOIN` these tables; the card shows "connect" until rows exist.
10. **Coverage first:** every headline sits under the 1.0 strip, so the reader sees how many seats send telemetry, how many people share text, and which heuristics are validated.

---

## 6. Actionable insights (rules in `tvf_insights`)

Each rule needs ≥ 14 days of data and the low-data minimums, and emits one concrete action. Token-type impacts (R1, R3) use `model_tiers` list prices because `cost_usd` is not split by token type; with no matching row the impact shows "—" and the rule ranks by turns affected. Evidence grain decides the drill: turn-grain rules → `/turns?insight_key=`, session-grain rules (R2b, R7) → `/sessions?insight_key=`.

**v1: R1, R2a, R2b, R4, R7, R9.** v1.1: R3, R5, R6, R8, R10, R11, R12.

| Rule | Trigger | Scope | Recommended action | Impact estimate |
|---|---|---|---|---|
| R1 Context bloat | median `cache_read_tokens` of the first A call per turn > 80k | person / squad | Run `/context` to see what fills the baseline. Trim CLAUDE.md; disable unused plugins and MCP servers (those seen in scope are listed from 6.2a) | `(median − 40k) × agent_calls_month × list_usd_per_mtok_cache_read / 1e6` (≤; the baseline is re-read on every agent call) |
| R2a Broken MCP server `beta` (tool_fail) | an MCP server's tool calls fail > 50% with ≥ 5 calls, or p95 > 5 s with ≥ 5 calls | server × squad | Disable MCP server: fix or remove `<server>` (`claude mcp remove <server>` or the project `.mcp.json`) | fail time per month (s) |
| R2b MCP connection failures (server unknown) | a person's `mcp_server_connection` failure rate > 50% with ≥ 5 attempts in 14 days | person (person and manager; exec sees the org count) | Run `/mcp` to find the server that fails to connect, then fix or remove it | `time_lost_s` per month |
| R3 Over-powered model (v1.1) `beta` + coverage | share of agent cost on `tier='large'` for `question`, `docs`, `ops` > 50%, n ≥ 20 text turns | squad / person | Model downgrade: default those workflows to the `medium` tier | `large_cost × (1 − medium_price / large_price)` (≤); suppressed without a price |
| R4 Permission friction | `user_reject` rate on a tool > 20% with ≥ 10 decisions | tool × squad | Add allow/deny rules in project `settings.json` and a CLAUDE.md rule on when that tool must not be used | rejects per month avoided |
| R5 Category failure (v1.1) `beta` + coverage | full friction rate for a category ≥ 1.5× the squad's rate over `T_text`, n ≥ 20, and squad text coverage ≥ 30% of turns with ≥ 3 people | category × squad | Write a CLAUDE.md rule or a skill for that workflow (e.g. "how we run tests here"); evidence = the 5 worst turns (derived fields for managers) | friction turns per month (scaled from the covered share; card says "estimated from x% text coverage") |
| R6 Thin prompts (v1.1) `beta` | person's clean rate for `<80` prompts ≤ half of their `300–1000` bucket, n ≥ 10 each | person (person and manager) | Coaching: share the prompt template (goal, files, constraints, done-criteria) | friction turns per month |
| R7 Cache-cold tax | person's `cold_share` > 40% | person | Coaching. If `cold_reason='start_or_resume'` dominates and ≥ 50% of sessions have ≤ 2 turns: resume sessions (`claude --continue` / `--resume`), batch related tasks. If `idle_gap` dominates: expect a cold call after > 5 min idle; for long breaks start a focused new session with `/compact` or a short handoff note instead of resuming a huge context | `SUM(cold_excess)` per month (≤) |
| R8 Overhead (v1.1) | **disablable** overhead (`prompt_suggestion` cost) > 10% of total cost | org / person | Turn off prompt suggestions in settings (exact key: **needs: verified settings key**, Day 1 check; the card shows the verified key or nothing). Session titles and auxiliary calls cannot be turned off and are not part of the trigger or the impact | disablable overhead cost per month |
| R9 Adoption gap | squad penetration < 50%, or a person not activated 14 days after `start_date` | squad / person | Coaching: enablement session; pair the person with a `power` user from 02 | headcount not activated |
| R10 Stale client (v1.1) | version older than latest − 2 minor | person | Update Claude Code (managed settings or `claude update`) | — |
| R11 Tool failures (v1.1) `beta` | tool failure rate > 30% with ≥ 20 calls | tool × squad | Fix the environment (missing binary, path, hook); add a SessionStart hook or a CLAUDE.md setup note | fail time per month |
| R12 Abandonment (v1.1) `beta` | abandoned turns > 10% of a person's closed turns, n ≥ 20 | person | Coaching: review 3 abandoned turns; check whether R4 or R11 apply | abandoned turns |

Ranking for 1.9 / 7.1: `impact_usd_month` where defined, else `impact_turns_month × median agent cost per turn`, else `impact_seconds_month` at the median turn duration. Insights with `uses_gated` rank below the others while their gate is closed. Ties go to the broader scope. Person-scoped insights never appear on exec views (§8).

---

## 7. Visual layout (DarwinLoop identity)

### 7.1 Tokens

```
--bg:           #0A0A0A   page background
--surface:      #141414   cards, table header            (derived)
--border:       #262626   1px borders, gridlines (non-text only)
--text:         #FAFAFA                                   (19.1:1 on --bg)
--muted:        #A1A1A1   secondary text, axis labels, low-data values (7.9:1 on --bg, 7.3:1 on --surface)
--primary:      #8ED563   good / clean / main series
--accent:       #199953   links, secondary series        (5.4:1 on --bg)
--cta:          #23F884   buttons (text #0A0A0A)
--warn:         #E5B341   warning, "beta" chip           (addition, not in brand)
--bad:          #F25F5C   friction / failure             (addition, not in brand)
--lowdata-mark: #3A3A3A   hatched fill / empty bar track only — never text

font-body:   Inter 400/600
font-mono:   JetBrains Mono 400/600 — numbers, KPIs, labels, chips, table numerics, page numbers
radius:      0 (cards, charts); 4px buttons and chips
shadow:      none
space:       4px base; card padding 16px; grid gap 16px; side gutter 16px mobile / 32px desktop
```

**Chart colour rules:**
- Default: categorical series use `--primary`, `--accent`, `--muted` in that order, max 3 hues. Status uses `--primary`/`--warn`/`--bad`. Axes and gridlines `--border`.
- **1.8 (4 segments), fixed:** useful `--primary` solid · cost in friction turns `--bad` diagonal hatch · cache-cold excess `--warn` dots · overhead `--muted` solid. Each segment is directly labelled (name, %, USD) under the bar.
- **2.4 (5 flags), fixed:** user_reject `--bad` solid · tool_fail `--warn` solid · fast_reprompt `--accent` solid · correction `--text` outline with cross-hatch · abandoned `--muted` diagonal hatch. Stack order fixed; legend uses the same swatches + patterns; tooltip lists all 5 counts.
- Patterns are SVG `<pattern>` fills at 4px pitch so segments differ without colour (colour-blind safe).
- **Low data:** value text in `--muted` + `low data` chip (outline `--muted`, mono 11px); bars use a `--lowdata-mark` hatched fill. Never `#3A3A3A` text.
- Bands render as text chips `low` / `typical` / `high` in `--muted` / `--text` / `--warn`, never numbers. `beta` chip: 4px-radius outline in `--warn`, mono 11px. Coverage chip: outline `--border`, text `--muted`, mono 11px (`text 38% · 9p`).
- Dark only in v1 (brand is dark-only); every text/background pair ≥ 4.5:1. Page titles use the numbered-step style `01 Overview` … `07 Insights` in JetBrains Mono, number in `--primary`.

### 7.2 Wireframes

**Frame (all pages)**

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [logo] DarwinLoop  01 Overview  02 Squads  06 Health  07 Insights   you@ ▾  │
├──────────────────────────────────────────────────────────────────────────────┤
│ [28d ▾ 2026-09-24 → 2026-10-21] [month: 2026-09 ▾] [squad ▾] [surface ▾] [model ▾] │
│ Org / Platform / Ana / 3f9c… / turn 12                    times: America/Sao_Paulo │
└──────────────────────────────────────────────────────────────────────────────┘
```

**01 Overview**

```
01 Overview
COVERAGE  telemetry 28/34 seats · text opt-in 9/28 people · gate ●fast ●tool ●aband ●corr ●cat · ETA 2026-11-12  [def]
┌────────────┬────────────┬──────────────┬────────────┬──────────────┬────────────────┐
│ WAU    def │ PENETRATION│ CLEAN [beta] │ $/ACTIVE/WK│ NO CC ACTIVITY│ CHANGE AFTER   │
│ 23  ▲+4    │ 68%        │ 84%  ▲2pp    │ $14        │ 6 of 34 seats │ ACTIONS  slot  │
│ ▁▂▃▅▆▇     │ 23/34      │ behavioural  │ API-equiv, │ may use chat/ │ appears 14 d   │
│ people,    │            │ n=1,942      │ not billed │ Cowork (n/a)  │ after first    │
│ not devices│            │ excl. open   │            │ (2026-09)     │ action done    │
│            │            │              │            │               │ 1 done → 11-05 │
└────────────┴────────────┴──────────────┴────────────┴──────────────┴────────────────┘
output proxy, not productivity · edit acceptance 88% · lines +12.4k / −3.1k (28d)
┌───────────────────────────────┬────────────────────────────────────┐
│ 1.3 ADOPTION BY SQUAD         │ 1.7 SEAT LEVERAGE (2026-09)         │
│ Platform ██████████ 90% 9/10  │ Claude Code only, lower bound       │
│ Data     ██████░░░░ 60% 6/10  │ Org      ───●──|──   0.9            │
│ Mobile   ███░░░░░░░ 30% 3/10  │ Platform ─────|─●─   1.4            │
│ other(<5)██░░░░░░░░ 25%       │ Data     ─●───|───   0.4            │
├───────────────────────────────┼────────────────────────────────────┤
│ 1.4 DEPTH (active days / 28d) │ 1.8 WHERE SPEND GOES (≤, API-equiv.)│
│ 1    ███                      │ [███████ useful|▨▨ fric|⁘⁘ cold|░ ov]│
│ 2-5  ██████                   │ useful 71% $1,204 · friction ≤12%   │
│ 6-12 ████████                 │ $203 · cache-cold 12% $198 ·        │
│ 13+  ██████                   │ overhead 5% $84 (disablable 3%)     │
├───────────────────────────────┴────────────────────────────────────┤
│ 1.14 ADOPTION FUNNEL (28d · each step ⊂ previous)                   │
│ seats      34 ████████████████████ 100%                             │
│ telemetry  28 ████████████████     82%  (−6)                        │
│ activated  26 ███████████████      76%  (−2)                        │
│ weekly     23 █████████████        68%  (−3)                        │
│ habitual    8 █████                24%  (−15)  ← biggest drop       │
│ deep        5 ███                  15%  (−3)                        │
├────────────────────────────────────────────────────────────────────┤
│ 1.4b REACH  MCP 41% · auto 22% · resume 57%                         │
├────────────────────────────────────────────────────────────────────┤
│ 1.9 TOP ACTIONS                                                     │
│ 01  Disable MCP "jira-local" — its tools failed 34/34 calls,        │
│     6 min waited/mo · Data squad                    [beta] [view →] │
│ 02  Trim context: baseline 112k tokens/call · org ≤$96/mo API-eq.   │
│                                                            [view →] │
│ 03  Enablement for Mobile — 7 of 10 not activated          [view →] │
├────────────────────────────────┬───────────────────────────────────┤
│ 1.10 OUTCOMES needs: GitHub ·  │ (v1.1) 1.13 TIME SAVED needs:     │
│ needs: Jira       [connect →]  │ survey                            │
└────────────────────────────────┴───────────────────────────────────┘
```

**02 Squad**

```
02 Squad · Data
┌──────────┬──────────────┬──────────────┬──────────┐
│ WAU 6/10 │ CLEAN 79%    │ $11/wk       │ EDIT ACC │
│          │ [beta] n=402 │ API-equiv.   │ 88%      │
└──────────┴──────────────┴──────────────┴──────────┘
┌────────────────────────────────────────────────────────────────────┐
│ 2.2 PEOPLE      (bands vs squad: low / typical / high)              │
│ name   last   days mcp auto text turns  $/wk   rej   clean  status  │
│ Carla   —       0   ·   ·   off   —      —      —     —   not activ.│
│ Bruno  10-21    6   ·   ✓   off  typ    typ    high  low   — [gate] │
│ Ana    10-22   14   ✓   ✓   on   high   high   low   high  power    │
├──────────────────────────────┬─────────────────────────────────────┤
│ 2.3 FRICTION BY CATEGORY beta│ 2.4 FRICTION MIX (flags/week)        │
│ text 41% · 4p                │ ■rej ■tool ■fast ▨corr(text 41%) ▧ab │
│ test     ████████ 41% n=24   │ ▆▆ ▇▅ ▆▆ ▅▅                          │
│ bugfix   █████ 27%  n=48     │                                      │
├──────────────────────────────┴─────────────────────────────────────┤
│ 2.6 TREND (12w)  clean ──  WAU ▁▂▃                                  │
└────────────────────────────────────────────────────────────────────┘
```

**03 Person** (manager view shown; self view adds the daily calendar, exact values and session times)

```
03 Person · Bruno (Data)       visible to: Bruno, Data manager · viewed by (2) · text: off
┌────────┬──────────┬────────┬────────┬────────┐
│ DAYS 6 │CLEAN low │TURN/SES│ LEN 64 │ $ typ  │   tick = squad median
│ |──●   │ beta     │ 1.8 ●| │ ●──|   │        │
└────────┴──────────┴────────┴────────┴────────┘
┌──────────────────────────────┬─────────────────────────────────────┐
│ 3.7 WEEKLY TREND (12w) beta  │ 3.3 PROMPT LENGTH vs CLEAN RATE      │
│ clean  low low typ typ       │ <80     low    sq typical            │
│ (b) needs: text opt-in       │ 80-300  typ    sq typical            │
├──────────────────────────────┼─────────────────────────────────────┤
│ 3.4 CACHE-COLD TAX  band high│ 3.2 ACTIVE WEEKS  ■ ■ □ ■            │
│ starts 70% · idle 30%        │                                      │
├──────────────────────────────┴─────────────────────────────────────┤
│ 3.5 SESSIONS   date  surface turns fric  type   model        [→]    │
│               10-21  cli     3–10  high  fresh  sonnet              │
├────────────────────────────────────────────────────────────────────┤
│ 3.8 WHAT YOUR MANAGER SEES                                          │
│ Bruno 10-21 6 · ✓ off typ typ high low  —                           │
└────────────────────────────────────────────────────────────────────┘
```

**04 Session / 05 Turn** (self view)

```
04 Session 3f9c… · Bruno · cli 2.1.4 · 14:02→14:41 · fresh · $0.62 API-eq. · cache 91%
┌────────────────────────────────────────────────────────────────────┐
│ 4.2 TIMELINE  [t1 ████]12s[t2 █]8s[t3 ██████]240s[t4 ███]           │
│               green=clean  red=friction  grey=abandoned             │
├────────────────────────────────────────────────────────────────────┤
│ 4.5 +120 −34 lines · edits 9 accepted / 1 rejected                  │
├────────────────────────────────────────────────────────────────────┤
│ TURNS  (the /turns list, session=3f9c…)                             │
└────────────────────────────────────────────────────────────────────┘

05 Turn 3 · bugfix · 64 chars · kw-3                [fast_reprompt 8s · reject] [user_reject]
┌────────────────────────────────────────────────────────────────────┐
│ 5.1 PROMPT   "roda o teste de novo"            (text expires 11-21) │
│ 5.2 WATERFALL                                                       │
│ #1 api_request  sonnet  in 3k  cache 104k  $0.01  ttft 900ms        │
│ #2 tool_decision Bash  reject  user_reject                          │
│ —  no tool_result, no assistant_response                            │
│ 5.5 NEXT → turn 4 · 8s later · correction [beta]                    │
└────────────────────────────────────────────────────────────────────┘
```

**List view `/turns`**

```
Turns · squad=Data · category=test · flag=friction   [× chips]      312 rows
┌────────────────────────────────────────────────────────────────────┐
│ date   person  session  cat   len     flags            calls fail model │
│ 10-21  Bruno   3f9c…    test  lt80    [tool_fail][fast] 4    2    sonnet│
│ ...                                                                 │
│                                        [← newer]  [older →]  50/page│
└────────────────────────────────────────────────────────────────────┘
```

**06 Health**

```
06 Health
┌──────────────────────────────┬─────────────────────────────────────┐
│ 6.1 TOOLS [beta]             │ 6.2a MCP SERVERS (from tool calls)   │
│ tool  calls fail p95 failtime│ server     calls fail p95  people    │
│ Bash  1.2k  6%  4.1s  9m     │ jira-local   34  100% 8.9s   4       │
├──────────────────────────────┴─────────────────────────────────────┤
│ 6.2b MCP CONNECTIONS (server unknown) 212 att · 31% fail · 41 min   │
│ by error_code ▇▅▂   by transport ▇▃   needs: server name attr       │
└────────────────────────────────────────────────────────────────────┘
```

**07 Insights** is one column of cards: an `NN  <action>` headline in JetBrains Mono, an evidence line in `--muted`, impact right-aligned, optional `beta` and coverage chips, buttons `[evidence →] [mark done] [dismiss]`. Done cards show the 7.2 before/after mini bars with "before/after, not causal".

Mobile (< 768px): one column; KPI rows 2 × 3; the coverage strip wraps to 3 lines; tables become stacked cards (name + 3 key values + "more"); the filter bar collapses to `[filters (3)]`; no horizontal page scroll (wide tables scroll inside their card); the definitions drawer becomes a bottom sheet.

---

## 8. Privacy and access

### 8.1 Roles and per-widget visibility

Identity is Google sign-in via IAP on `darwinloop-dashboard`, domain-restricted. Role from `people.role`.

| Viewer | Org/squad aggregates | Person / session / turn / lists | Prompt/response text |
|---|---|---|---|
| `dev` | yes (k-anon, §8.2) | own only, exact values | own only |
| `manager` | own squad full; other squads k-anon only | people where `people.manager_email = viewer`, or the same squad when `squad_lead`; matrix below | **never** |
| `exec` | yes, k-anon only | **no** (lock) | no |
| `admin` | yes | yes, exact, every access logged | only with a recorded reason (support, incident, `heuristic-validation`), logged as `level='text'` |

**Manager matrix (what a manager sees about a person; self and admin always see exact values):**

| Widget | Manager sees | Hidden from manager |
|---|---|---|
| 2.2 / 3.8 row | bands, flags, status badges | exact turns, cost, rates |
| 3.1 | active days, turns/session, median prompt length (exact); clean rate and cost as bands | exact clean rate, exact cost |
| 3.2 | active yes/no per ISO week | daily calendar, turns/day |
| 3.3 | band per length bucket vs squad | exact rates |
| 3.4 | `cold_share` band, start/idle split % | USD |
| 3.5 / `/sessions` | date, surface, turns bucket, friction band, failing tool calls, start_type, main model | start time, duration, exact cost, lines |
| 3.7 | (a) weekly band series; (b) only if text-backed, as bands | exact weekly rates |
| 4.1 | date, surface, version, start_type, permission modes, cost band, cache hit | start/end time, exact cost |
| 4.2 | equal-width turn blocks with colour | durations, gap seconds |
| 4.5 | — | whole widget |
| `/turns` | date, category, length bucket, flags, call counts, model | time of day, cost |
| 5.1 / 5.4 | derived labels only | text |
| 5.2 | event types, model, tokens, tool names, success, tool duration, ttft | cost, timestamps |
| 5.5 | gap as `< 60 s` / `≥ 60 s` | exact gap |

The API enforces this server-side: each widget query has a `manager` projection that drops or bands the hidden columns before the response; the front end never receives them. `day=` and `sort=cost_desc` on list views return 403 for managers.

### 8.2 k-anonymity (one rule everywhere)

Any squad-level aggregate shown to an exec, or to a manager looking at another squad, groups by `v_squad_k.display_squad`. Squads with `active_headcount < config.k_anon_min` (5) merge into "other"; if "other" itself is < k it is suppressed ("hidden (< k)"). Applies to 1.3, 1.7, 1.13, 1.14, 6.4, 6.6, 6.9, the drawer splits of 1.4/1.5, and any squad breakdown in 06/07. Org-wide numbers need ≥ k active people. Person-level bands (2.2, 3.x for managers) need ≥ k comparable people in the squad (§3, 2.2). Person names in 6.2a/6.2b are replaced by a count for these viewers. The coverage chip's people count is shown as "< 5" below k for these viewers.

### 8.3 Other rules

- **Text capture is opt-in per person and enforced at ingest**, not by client config: `people.text_opt_in` must be true *and* the person must set `OTEL_LOG_USER_PROMPTS=1` locally (§4.5). For everyone else the ingest discards `prompt` and `response` text unread; no `raw_text` row, no heuristics. Managed settings never enable prompt logging.
- **Withdrawal:** the admin sets `text_opt_in=false`; within 5 minutes the ingest stops keeping text. On request, the person's `raw_text` rows are deleted with the §8.4 procedure (step 3, `raw_text` only). Derived fields already computed stay (they contain no text).
- **Access log:** every person, session, turn and list view writes `access_log`. The person sees who viewed their data (03 header, 3.8).
- **Text is never shown to managers or execs.** Coaching uses derived signals.
- **Retention:** `raw_text` 30 days via partition expiration (BigQuery-enforced). `raw_events`/`raw_metrics` 400 days, `access_log` 400 days, `ingest_rejects` 90 days. Time travel 48 h; BigQuery's 7-day fail-safe is stated in the team notice.
- **Ingest minimisation:** no file paths or command content are sent or stored. `user.email` is stored only in `raw_events`, `raw_text`, `raw_metrics` and `people`. URLs and exports use `person_id`.
- **`person_id` is pseudonymous, not anonymous:** an unsalted SHA-256 of the email can be recomputed by anyone holding the staff list, so it is treated as personal data everywhere (access rules, erasure). shortcut: plain SHA-256 keeps `v_person` a one-line join; upgrade to HMAC with a Secret Manager pepper if `person_id` ever leaves the dataset.
- **Purpose limitation** (dashboard footer and team notice): data is used to improve AI tooling, enablement and cost. It is **not** used for performance evaluation, ranking or compensation. No leaderboard; 2.2 is sorted by who needs help; person-level signals reach managers as bands; `may need support` is a coaching prompt, gated on validated signals and repeated weeks.

### 8.4 LGPD notes

- **Legal basis:** legitimate interest (art. 7, IX) for tooling improvement and cost governance, with a documented LIA. Text capture additionally rests on the person's recorded opt-in (`text_opt_in_at` + the written request), revocable at any time.
- **Transparency (art. 9):** a plain-Portuguese team notice before rollout: signals collected, that text is collected only from people who opt in, purposes, retention (incl. 48 h time travel and 7-day fail-safe), and who sees what (§8.1 matrix).
- **Data subject rights (art. 18):** view own data (03–05, 3.8), export (CSV of own `tvf_turns`/`tvf_sessions`), withdraw text opt-in, request deletion. SLA 15 days.
- **Deletion procedure** (admin, `scripts/erase_subject.py`, logged):
  1. Insert `person_id` and the person's `account_uuids` into `deleted_subjects`. The ingest drops new records and every view hides the person immediately.
  2. Wait until the person's last streamed row is older than 90 minutes (streaming buffer; BigQuery rejects `DELETE` on buffered rows).
  3. `DELETE ... WHERE person_id = @pid OR user_email = @e OR account_uuid IN UNNEST(@acct)` (covers every device and both surfaces) on `raw_events`, `raw_text`, `raw_metrics`, `survey_responses`, `claude_ai_usage`; delete the `people` row and `heuristic_labels` rows for their turns; NULL `insight_status.owner_email` where theirs.
  4. `access_log`: rows where they are the **target** keep the record (accountability, art. 37) with `target_person_id` replaced by `deleted:<random>`; rows where they are the **viewer** are deleted.
  5. Verify `COUNT(*) = 0` per table; retry after 90 minutes if not. Set `completed_at`. Unrecoverable after time travel (48 h) and fail-safe (7 days), inside the SLA.
- **Minimisation:** text only from opted-in people, kept 30 days; derived fields afterwards. No sensitive data categories intended; the tone heuristic does not infer health, religion, etc. `assistant_response` text is treated like prompt text because it may contain client code and data.
- **Location:** dataset in `southamerica-east1`. Processor: Google Cloud (GCP DPA). Anthropic receives prompts as part of normal product use, which this dashboard does not change.
- **Controller/DPO:** name the Brain3 encarregado in the notice. **needs: DPO contact** before rollout.
