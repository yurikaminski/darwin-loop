-- Derived model over raw_events / raw_metrics (spec v5 §4.2). Apply with: bq query --use_legacy_sql=false < views.sql
-- OTLP sends most numbers as strings, hence SAFE_CAST everywhere. Local day = America/Sao_Paulo.
-- shortcut: plain views recomputed per request, not the spec's date-parameterised TVFs; switch when raw_events > ~10 GB
-- or a page takes > 3 s.
-- Thresholds (config): cache_ttl_s 300, resume_gap_s 21600, fast_reprompt_s 60, followup_window_s 1800,
-- open_turn_grace_s 1800.

-- AI mood per closed turn (-2 very disappointed .. 2 happy), written by POST /api/mood. Holds no text, so it does not expire.
CREATE TABLE IF NOT EXISTS `brain003-mvp.darwinloop_telemetry.turn_mood` (
  prompt_id STRING, session_id STRING, mood INT64, model STRING, scored_at TIMESTAMP);

CREATE OR REPLACE VIEW `brain003-mvp.darwinloop_telemetry.v_events` AS
SELECT e.*, COALESCE(p.squad, e.team, 'unassigned') AS squad, COALESCE(p.name, e.user_email) AS person,
       JSON_VALUE(attrs, '$.query_source') AS query_source,
       JSON_VALUE(attrs, '$.query_source') IN ('prompt_suggestion', 'generate_session_title', 'auxiliary') AS is_aux
FROM `brain003-mvp.darwinloop_telemetry.raw_events` e
LEFT JOIN `brain003-mvp.darwinloop_telemetry.people` p ON LOWER(p.email) = LOWER(e.user_email)
WHERE e.event_name NOT IN ('plugin_loaded', 'hook_registered', 'hook_execution_start', 'hook_execution_complete',
                           'managed_settings_resolved');

-- One row per api_request. Agent calls = main loop; everything else is overhead.
CREATE OR REPLACE VIEW `brain003-mvp.darwinloop_telemetry.v_calls` AS
SELECT *,
       is_agent AND (prev_agent_gap_s IS NULL OR prev_agent_gap_s > 300) AS is_cold,
       IF(prev_agent_gap_s IS NOT NULL AND prev_agent_gap_s <= 21600, 'idle_gap', 'start_or_resume') AS cold_reason,
       CASE WHEN is_agent THEN NULL WHEN query_source = 'prompt_suggestion' THEN 'disablable' ELSE 'fixed' END AS overhead_kind
FROM (
  SELECT ts, DATE(ts, 'America/Sao_Paulo') AS day, session_id, prompt_id, user_email, person, squad,
         service_name AS surface, query_source, is_agent,
         JSON_VALUE(attrs, '$.model') AS model,
         IFNULL(SAFE_CAST(JSON_VALUE(attrs, '$.cost_usd') AS FLOAT64), 0) AS cost_usd,
         IFNULL(SAFE_CAST(JSON_VALUE(attrs, '$.input_tokens') AS INT64), 0) AS input_tokens,
         IFNULL(SAFE_CAST(JSON_VALUE(attrs, '$.output_tokens') AS INT64), 0) AS output_tokens,
         IFNULL(SAFE_CAST(JSON_VALUE(attrs, '$.cache_read_tokens') AS INT64), 0) AS cache_read_tokens,
         IFNULL(SAFE_CAST(JSON_VALUE(attrs, '$.cache_creation_tokens') AS INT64), 0) AS cache_creation_tokens,
         SAFE_CAST(JSON_VALUE(attrs, '$.duration_ms') AS INT64) AS duration_ms,
         TIMESTAMP_DIFF(ts, LAG(ts) OVER (PARTITION BY session_id, is_agent ORDER BY ts, seq), SECOND) AS prev_agent_gap_s
  FROM (SELECT *, IFNULL(query_source, 'main') IN ('sdk', 'main') AS is_agent
        FROM `brain003-mvp.darwinloop_telemetry.v_events` WHERE event_name = 'api_request'));

-- One row per turn (prompt.id). Flags are NULL while the turn is open (session active in the last 30 min).
CREATE OR REPLACE VIEW `brain003-mvp.darwinloop_telemetry.v_turns` AS
WITH base AS (
  SELECT prompt_id, ANY_VALUE(session_id) AS session_id, ANY_VALUE(user_email) AS user_email,
         ANY_VALUE(person) AS person, ANY_VALUE(squad) AS squad, ANY_VALUE(service_name) AS surface,
         COALESCE(MIN(IF(event_name = 'user_prompt', ts, NULL)), MIN(ts)) AS start_ts, MAX(ts) AS end_ts,
         ANY_VALUE(IF(event_name = 'user_prompt', SAFE_CAST(JSON_VALUE(attrs, '$.prompt_length') AS INT64), NULL)) AS prompt_length,
         ANY_VALUE(IF(event_name = 'user_prompt', JSON_VALUE(attrs, '$.dl_category'), NULL)) AS category,
         ANY_VALUE(IF(event_name = 'user_prompt', JSON_VALUE(attrs, '$.dl_domain'), NULL)) AS domain,
         ANY_VALUE(JSON_VALUE(attrs, '$.dl_project')) AS project,
         ANY_VALUE(IF(event_name = 'user_prompt', JSON_VALUE(attrs, '$.dl_tone'), NULL)) AS tone,
         ANY_VALUE(IF(event_name = 'user_prompt', SAFE_CAST(JSON_VALUE(attrs, '$.dl_correction') AS BOOL), NULL)) AS correction_kw,
         ANY_VALUE(IF(event_name = 'user_prompt', JSON_VALUE(attrs, '$.dl_heuristic_version'), NULL)) AS heuristic_version,
         COUNTIF(event_name = 'tool_result') AS n_tool_calls,
         COUNTIF(event_name = 'tool_result' AND JSON_VALUE(attrs, '$.success') = 'false') AS n_tool_fail,
         SUM(IF(event_name = 'tool_result' AND JSON_VALUE(attrs, '$.success') = 'false',
                SAFE_CAST(JSON_VALUE(attrs, '$.duration_ms') AS INT64), 0)) AS fail_time_ms,
         COUNTIF(event_name = 'tool_decision' AND (JSON_VALUE(attrs, '$.source') = 'user_reject'
                 OR (JSON_VALUE(attrs, '$.decision') = 'reject' AND JSON_VALUE(attrs, '$.source') != 'config'))) AS n_user_reject,
         COUNTIF(event_name = 'tool_decision' AND JSON_VALUE(attrs, '$.decision') = 'reject'
                 AND JSON_VALUE(attrs, '$.source') = 'config') AS n_policy_block,
         COUNTIF(event_name = 'api_error') AS n_api_errors,
         LOGICAL_OR(event_name = 'assistant_response' AND IFNULL(query_source, 'main') IN ('sdk', 'main')) AS has_response
  FROM `brain003-mvp.darwinloop_telemetry.v_events`
  WHERE prompt_id IS NOT NULL
  GROUP BY prompt_id),
calls AS (
  SELECT prompt_id, COUNTIF(is_agent) AS n_agent_calls,
         SUM(IF(is_agent, cost_usd, 0)) AS agent_cost, SUM(IF(is_agent, 0, cost_usd)) AS overhead_cost,
         SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens,
         SUM(cache_read_tokens) AS cache_read_tokens, SUM(cache_creation_tokens) AS cache_creation_tokens,
         LOGICAL_OR(is_cold) AS has_cold,
         ARRAY_AGG(IF(is_agent, model, NULL) IGNORE NULLS ORDER BY cost_usd DESC LIMIT 1)[SAFE_OFFSET(0)] AS main_model
  FROM `brain003-mvp.darwinloop_telemetry.v_calls` GROUP BY prompt_id),
-- vcs.repository.name only rides on some events (plugin_loaded, hooks; not user_prompt, often no prompt_id), so take it per session.
sp AS (
  SELECT session_id, ANY_VALUE(JSON_VALUE(attrs, '$.dl_project')) AS session_project
  FROM `brain003-mvp.darwinloop_telemetry.v_events`
  WHERE JSON_VALUE(attrs, '$.dl_project') IS NOT NULL GROUP BY session_id),
w AS (
  SELECT b.* REPLACE (COALESCE(b.project, sp.session_project) AS project), c.* EXCEPT (prompt_id), DATE(b.start_ts, 'America/Sao_Paulo') AS day, b.category IS NOT NULL AS has_text,
         ROW_NUMBER() OVER s AS turn_no,
         TIMESTAMP_DIFF(LEAD(b.start_ts) OVER s, b.end_ts, SECOND) AS next_gap_s,
         LEAD(b.category IS NOT NULL) OVER s AS next_has_text_raw, LEAD(b.correction_kw) OVER s AS next_correction_raw,
         LEAD(b.prompt_id) OVER s IS NULL AS is_last,
         MAX(b.end_ts) OVER (PARTITION BY b.session_id) AS session_last_ts
  FROM base b LEFT JOIN calls c USING (prompt_id) LEFT JOIN sp USING (session_id)
  WINDOW s AS (PARTITION BY b.session_id ORDER BY b.start_ts)),
st AS (
  SELECT * EXCEPT (next_has_text_raw, next_correction_raw),
         IF(next_gap_s <= 1800, next_has_text_raw, NULL) AS next_has_text,
         IF(next_gap_s <= 1800, next_correction_raw, NULL) AS next_correction_kw,
         IF(is_last AND TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), session_last_ts, SECOND) < 1800, 'open', 'closed') AS turn_state
  FROM w),
f AS (
  SELECT *,
         IF(turn_state = 'open', NULL, n_user_reject > 0) AS flag_user_reject,
         IF(turn_state = 'open', NULL, n_tool_fail > 0) AS flag_tool_fail,
         -- PM must_fix (kw-4): behavioural only, no text cue, so managers see identical numbers with or without opt-in text.
         IF(turn_state = 'open', NULL, IFNULL(next_gap_s < 60, FALSE)
            AND (NOT has_response OR n_user_reject > 0 OR n_tool_fail > 0)) AS flag_fast_reprompt,
         IF(turn_state = 'open', NULL, NOT has_response AND (next_gap_s IS NULL OR next_gap_s > 1800)) AS flag_abandoned
  FROM st)
SELECT *,
       flag_user_reject OR flag_tool_fail OR flag_fast_reprompt OR flag_abandoned AS is_friction_b,
       (flag_user_reject OR flag_tool_fail OR flag_fast_reprompt OR flag_abandoned)
         OR (turn_state = 'closed' AND next_correction_kw IS TRUE) AS is_friction,
       CASE WHEN NOT has_response THEN 'no_answer' WHEN n_user_reject > 0 THEN 'reject' WHEN n_tool_fail > 0 THEN 'tool_fail'
       END AS fast_reprompt_reason
FROM f LEFT JOIN (  -- concurrent scorers may write a turn twice; any score wins
  SELECT prompt_id, ANY_VALUE(mood) AS mood FROM `brain003-mvp.darwinloop_telemetry.turn_mood` GROUP BY 1) USING (prompt_id);

-- Exclusive spend split per api_request: overhead > cold excess > friction > useful (segments sum to the total).
CREATE OR REPLACE VIEW `brain003-mvp.darwinloop_telemetry.v_cost_alloc` AS
WITH ref AS (
  SELECT model, APPROX_QUANTILES(cost_usd, 2)[OFFSET(1)] AS ref_cost
  FROM `brain003-mvp.darwinloop_telemetry.v_calls` WHERE is_agent AND NOT is_cold GROUP BY model),
a AS (
  SELECT c.*, t.is_friction_b,
         IF(NOT c.is_agent, c.cost_usd, 0) AS overhead,
         IF(c.is_cold, GREATEST(c.cost_usd - IFNULL(r.ref_cost, c.cost_usd), 0), 0) AS cold_excess
  FROM `brain003-mvp.darwinloop_telemetry.v_calls` c
  LEFT JOIN `brain003-mvp.darwinloop_telemetry.v_turns` t USING (prompt_id)
  LEFT JOIN ref r USING (model))
SELECT *, IF(is_agent AND is_friction_b IS TRUE, cost_usd - cold_excess, 0) AS friction,
       cost_usd - overhead - cold_excess - IF(is_agent AND is_friction_b IS TRUE, cost_usd - cold_excess, 0) AS useful
FROM a;

-- One row per session.
CREATE OR REPLACE VIEW `brain003-mvp.darwinloop_telemetry.v_sessions` AS
WITH t AS (
  SELECT session_id, ANY_VALUE(user_email) AS user_email, ANY_VALUE(person) AS person, ANY_VALUE(squad) AS squad,
         ANY_VALUE(surface) AS surface, MIN(start_ts) AS start_ts, MAX(end_ts) AS end_ts,
         MIN(day) AS day, COUNT(*) AS n_turns, COUNTIF(turn_state = 'closed') AS n_closed,
         COUNTIF(is_friction_b) AS n_friction_b, SUM(n_user_reject) AS n_user_reject, SUM(n_tool_fail) AS n_tool_fail,
         COUNTIF(flag_abandoned) AS n_abandoned, COUNTIF(next_correction_kw) AS n_corrections,
         SUM(n_api_errors) AS n_api_errors,
         SUM(cache_read_tokens) / NULLIF(SUM(input_tokens + cache_read_tokens + cache_creation_tokens), 0) AS cache_hit,
         SUM(input_tokens + output_tokens + cache_read_tokens + cache_creation_tokens) AS tokens,
         ARRAY_AGG(DISTINCT main_model IGNORE NULLS) AS models,
         APPROX_TOP_COUNT(domain, 2) AS domain_top, APPROX_TOP_COUNT(project, 2) AS project_top,
         LOGICAL_OR(turn_state = 'open') AS is_live, ROUND(AVG(mood)) AS mood
  FROM `brain003-mvp.darwinloop_telemetry.v_turns` GROUP BY session_id),
c AS (
  SELECT session_id, SUM(cost_usd) AS cost_usd, SUM(IF(is_agent, cost_usd, 0)) AS agent_cost, SUM(overhead) AS overhead_cost,
         SUM(cold_excess) AS cold_excess, SUM(friction) AS friction_cost
  FROM `brain003-mvp.darwinloop_telemetry.v_cost_alloc` GROUP BY session_id)
SELECT t.* EXCEPT (domain_top, project_top),
       -- session domain = most frequent tagged domain among its prompts (top-2 so an untagged majority can't hide it)
       (SELECT d.value FROM UNNEST(domain_top) d WHERE d.value IS NOT NULL ORDER BY d.count DESC LIMIT 1) AS domain,
       (SELECT d.value FROM UNNEST(project_top) d WHERE d.value IS NOT NULL ORDER BY d.count DESC LIMIT 1) AS project,
       IFNULL(c.cost_usd, 0) AS cost_usd, IFNULL(c.agent_cost, 0) AS agent_cost,
       IFNULL(c.overhead_cost, 0) AS overhead_cost, IFNULL(c.cold_excess, 0) AS cold_excess,
       IFNULL(c.friction_cost, 0) AS friction_cost
FROM t LEFT JOIN c USING (session_id);

-- One row per person per local day; page KPIs aggregate from here.
CREATE OR REPLACE VIEW `brain003-mvp.darwinloop_telemetry.v_person_day` AS
WITH t AS (
  SELECT day, LOWER(user_email) AS user_email, ANY_VALUE(person) AS person, ANY_VALUE(squad) AS squad,
         ANY_VALUE(surface) AS surface, COUNT(DISTINCT session_id) AS sessions, COUNT(*) AS turns,
         COUNTIF(turn_state = 'closed') AS closed_turns, COUNTIF(has_text) AS text_turns,
         COUNTIF(is_friction_b) AS friction_b, COUNTIF(is_friction AND has_text) AS friction_text,
         COUNTIF(flag_user_reject) AS reject_turns, COUNTIF(flag_tool_fail) AS tool_fail_turns,
         COUNTIF(flag_fast_reprompt) AS fast_reprompt_turns, COUNTIF(flag_abandoned) AS abandoned_turns,
         COUNTIF(next_correction_kw) AS corrections, COUNTIF(next_has_text) AS next_text_turns,
         SUM(n_user_reject) AS user_rejects, SUM(n_tool_calls) AS tool_calls, SUM(n_tool_fail) AS tool_fails,
         APPROX_QUANTILES(prompt_length, 2)[OFFSET(1)] AS median_prompt_length
  FROM `brain003-mvp.darwinloop_telemetry.v_turns` GROUP BY 1, 2),
c AS (
  SELECT day, LOWER(user_email) AS user_email, SUM(cost_usd) AS cost_usd, SUM(IF(is_agent, cost_usd, 0)) AS agent_cost,
         SUM(overhead) AS overhead_cost, SUM(IF(overhead_kind = 'disablable', overhead, 0)) AS disablable_overhead,
         SUM(cold_excess) AS cold_excess, SUM(friction) AS friction_cost, SUM(useful) AS useful_cost,
         COUNTIF(is_agent) AS agent_calls, COUNTIF(is_cold) AS cold_calls,
         SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens,
         SUM(cache_read_tokens) AS cache_read_tokens, SUM(cache_creation_tokens) AS cache_creation_tokens
  FROM `brain003-mvp.darwinloop_telemetry.v_cost_alloc` GROUP BY 1, 2),
m AS (
  SELECT DATE(ts, 'America/Sao_Paulo') AS day, LOWER(user_email) AS user_email,
         SUM(IF(name = 'lines_of_code.count' AND JSON_VALUE(attrs, '$.type') = 'added', value, 0)) AS lines_added,
         SUM(IF(name = 'lines_of_code.count' AND JSON_VALUE(attrs, '$.type') = 'removed', value, 0)) AS lines_removed,
         SUM(IF(name = 'active_time.total', value, 0)) AS active_s,
         SUM(IF(name = 'commit.count', value, 0)) AS commits,
         SUM(IF(name = 'pull_request.count', value, 0)) AS prs,
         SUM(IF(name = 'code_edit_tool.decision' AND JSON_VALUE(attrs, '$.decision') = 'accept', value, 0)) AS edits_accept,
         SUM(IF(name = 'code_edit_tool.decision' AND JSON_VALUE(attrs, '$.decision') = 'reject', value, 0)) AS edits_reject
  FROM `brain003-mvp.darwinloop_telemetry.raw_metrics` GROUP BY 1, 2),
x AS (
  SELECT DATE(ts, 'America/Sao_Paulo') AS day, LOWER(user_email) AS user_email,
         LOGICAL_OR(event_name = 'mcp_server_connection' AND JSON_VALUE(attrs, '$.status') = 'connected') AS uses_mcp,
         LOGICAL_OR(event_name = 'permission_mode_changed' AND JSON_VALUE(attrs, '$.to_mode') = 'auto') AS uses_auto,
         COUNTIF(event_name = 'mcp_server_connection') AS mcp_attempts,
         COUNTIF(event_name = 'mcp_server_connection' AND JSON_VALUE(attrs, '$.status') = 'failed') AS mcp_failures
  FROM `brain003-mvp.darwinloop_telemetry.raw_events` GROUP BY 1, 2)
SELECT day, user_email, t.person, t.squad, t.surface,
       IFNULL(t.sessions, 0) AS sessions, IFNULL(t.turns, 0) AS turns, IFNULL(t.closed_turns, 0) AS closed_turns,
       IFNULL(t.text_turns, 0) AS text_turns, IFNULL(t.friction_b, 0) AS friction_b,
       IFNULL(t.friction_text, 0) AS friction_text, IFNULL(t.reject_turns, 0) AS reject_turns,
       IFNULL(t.tool_fail_turns, 0) AS tool_fail_turns, IFNULL(t.fast_reprompt_turns, 0) AS fast_reprompt_turns,
       IFNULL(t.abandoned_turns, 0) AS abandoned_turns, IFNULL(t.corrections, 0) AS corrections,
       IFNULL(t.next_text_turns, 0) AS next_text_turns, IFNULL(t.user_rejects, 0) AS user_rejects,
       IFNULL(t.tool_calls, 0) AS tool_calls, IFNULL(t.tool_fails, 0) AS tool_fails,
       t.median_prompt_length,
       IFNULL(c.cost_usd, 0) AS cost_usd, IFNULL(c.agent_cost, 0) AS agent_cost, IFNULL(c.overhead_cost, 0) AS overhead_cost,
       IFNULL(c.disablable_overhead, 0) AS disablable_overhead, IFNULL(c.cold_excess, 0) AS cold_excess,
       IFNULL(c.friction_cost, 0) AS friction_cost, IFNULL(c.useful_cost, 0) AS useful_cost,
       IFNULL(c.agent_calls, 0) AS agent_calls, IFNULL(c.cold_calls, 0) AS cold_calls,
       IFNULL(c.input_tokens, 0) AS input_tokens, IFNULL(c.output_tokens, 0) AS output_tokens,
       IFNULL(c.cache_read_tokens, 0) AS cache_read_tokens, IFNULL(c.cache_creation_tokens, 0) AS cache_creation_tokens,
       IFNULL(m.lines_added, 0) AS lines_added, IFNULL(m.lines_removed, 0) AS lines_removed,
       IFNULL(m.active_s, 0) AS active_s, IFNULL(m.commits, 0) AS commits, IFNULL(m.prs, 0) AS prs,
       IFNULL(m.edits_accept, 0) AS edits_accept, IFNULL(m.edits_reject, 0) AS edits_reject,
       IFNULL(x.uses_mcp, FALSE) AS uses_mcp, IFNULL(x.uses_auto, FALSE) AS uses_auto,
       IFNULL(x.mcp_attempts, 0) AS mcp_attempts, IFNULL(x.mcp_failures, 0) AS mcp_failures
FROM t FULL JOIN c USING (day, user_email) FULL JOIN m USING (day, user_email) LEFT JOIN x USING (day, user_email)
WHERE user_email IS NOT NULL;
