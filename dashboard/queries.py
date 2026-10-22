"""Named read-only queries behind /api/{name}. Params: @start @end @squad @surface @email @model @session @prompt."""

# Shared filter for day-grained views (v_person_day, v_turns, v_sessions).
F = """day BETWEEN @start AND @end
  AND (@squad IS NULL OR squad = @squad) AND (@surface IS NULL OR surface = @surface)
  AND (@email IS NULL OR LOWER(user_email) = LOWER(@email))"""
FM = F + " AND (@model IS NULL OR main_model = @model)"

QUERIES = {
    # 01 Overview: one row of org KPIs; ratios are derived client-side so the drawer shows raw counts.
    "overview": f"""
WITH p AS (SELECT * FROM {{ds}}.v_person_day WHERE {F}),
u AS (SELECT user_email, COUNT(DISTINCT IF(turns > 0, day, NULL)) AS days_active,
             LOGICAL_OR(uses_mcp) AS mcp, LOGICAL_OR(uses_auto) AS auto, SUM(commits + prs) AS ships
      FROM p GROUP BY 1 HAVING SUM(turns) > 0)
SELECT (SELECT COUNT(*) FROM {{ds}}.people WHERE (@squad IS NULL OR squad = @squad)
          AND IFNULL(active_from, DATE '2000-01-01') <= CURRENT_DATE('America/Sao_Paulo')) AS roster,
       (SELECT COUNT(*) FROM u) AS active,
       (SELECT COUNT(DISTINCT user_email) FROM p
          WHERE turns > 0 AND day > DATE_SUB(CURRENT_DATE('America/Sao_Paulo'), INTERVAL 7 DAY)) AS wau,
       (SELECT COUNTIF(days_active >= 3) FROM u) AS habitual,
       (SELECT COUNTIF(days_active >= 3 AND (mcp OR auto OR ships > 0)) FROM u) AS power,
       (SELECT COUNTIF(mcp) FROM u) AS reach_mcp, (SELECT COUNTIF(auto) FROM u) AS reach_auto,
       (SELECT COUNTIF(ships > 0) FROM u) AS reach_ship,
       SUM(turns) AS turns, SUM(closed_turns) AS closed_turns, SUM(friction_b) AS friction_b, SUM(sessions) AS sessions,
       SUM(cost_usd) AS cost, SUM(useful_cost) AS useful, SUM(friction_cost) AS friction, SUM(cold_excess) AS cold,
       SUM(overhead_cost) AS overhead, SUM(disablable_overhead) AS disablable,
       SUM(edits_accept) AS edits_accept, SUM(edits_reject) AS edits_reject,
       SUM(lines_added) AS lines_added, SUM(lines_removed) AS lines_removed, SUM(commits) AS commits, SUM(prs) AS prs,
       SUM(agent_calls) AS agent_calls, SUM(cold_calls) AS cold_calls,
       SUM(tool_calls) AS tool_calls, SUM(tool_fails) AS tool_fails,
       SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens, SUM(input_tokens + output_tokens + cache_read_tokens + cache_creation_tokens) AS tokens
FROM p""",

    "trend": f"""
SELECT day, COUNT(DISTINCT IF(turns > 0, user_email, NULL)) AS active, SUM(turns) AS turns,
       SUM(closed_turns) AS closed_turns, SUM(friction_b) AS friction_b, SUM(cost_usd) AS cost,
       SUM(tool_calls) AS tool_calls, SUM(tool_fails) AS tool_fails, SUM(input_tokens + output_tokens + cache_read_tokens + cache_creation_tokens) AS tokens
FROM {{ds}}.v_person_day WHERE {F} GROUP BY day ORDER BY day""",

    # 02 Squads: adoption + quality + spend per squad (k-anonymity enforced client-side at < 5 people).
    "squads": f"""
WITH p AS (SELECT * FROM {{ds}}.v_person_day WHERE {F}),
r AS (SELECT squad, COUNT(*) AS roster FROM {{ds}}.people GROUP BY 1)
SELECT squad, ANY_VALUE(r.roster) AS roster, COUNT(DISTINCT IF(turns > 0, user_email, NULL)) AS active,
       SUM(turns) AS turns, SUM(closed_turns) AS closed_turns, SUM(friction_b) AS friction_b,
       SUM(cost_usd) AS cost, SUM(useful_cost) AS useful, SUM(friction_cost) AS friction, SUM(cold_excess) AS cold,
       SUM(overhead_cost) AS overhead, SUM(agent_calls) AS agent_calls, SUM(cold_calls) AS cold_calls,
       SUM(lines_added) AS lines_added, SUM(edits_accept) AS edits_accept, SUM(edits_reject) AS edits_reject, SUM(input_tokens + output_tokens + cache_read_tokens + cache_creation_tokens) AS tokens
FROM p LEFT JOIN r USING (squad) GROUP BY squad ORDER BY cost DESC""",

    # 03 Person list (within squad filter) and per-person daily series.
    "people": f"""
SELECT user_email, ANY_VALUE(person) AS person, ANY_VALUE(squad) AS squad,
       COUNT(DISTINCT IF(turns > 0, day, NULL)) AS days_active, MAX(IF(turns > 0, day, NULL)) AS last_day,
       SUM(sessions) AS sessions, SUM(turns) AS turns, SUM(closed_turns) AS closed_turns, SUM(friction_b) AS friction_b,
       SUM(reject_turns) AS reject_turns, SUM(tool_fail_turns) AS tool_fail_turns, SUM(abandoned_turns) AS abandoned_turns,
       SUM(cost_usd) AS cost, SUM(useful_cost) AS useful, SUM(friction_cost) AS friction, SUM(cold_excess) AS cold,
       SUM(overhead_cost) AS overhead, SUM(agent_calls) AS agent_calls, SUM(cold_calls) AS cold_calls,
       SUM(lines_added) AS lines_added, SUM(edits_accept) AS edits_accept, SUM(edits_reject) AS edits_reject,
       SUM(commits) AS commits, SUM(prs) AS prs, LOGICAL_OR(uses_mcp) AS uses_mcp, LOGICAL_OR(uses_auto) AS uses_auto
FROM {{ds}}.v_person_day WHERE {F} GROUP BY user_email ORDER BY cost DESC""",

    "categories": f"""
SELECT IFNULL(category, 'no text') AS category, COUNT(*) AS turns, COUNTIF(is_friction_b) AS friction_b,
       COUNTIF(turn_state = 'closed') AS closed_turns, SUM(agent_cost) AS cost, SUM(input_tokens + output_tokens + cache_read_tokens + cache_creation_tokens) AS tokens
FROM {{ds}}.v_turns WHERE {FM} GROUP BY 1 ORDER BY turns DESC""",

    "projects": f"""
SELECT IF(surface = 'cowork', 'Cowork', 'Claude Code') AS tool, project IS NOT NULL AS in_project,
       IFNULL(project, 'outside a project') AS project, COUNT(DISTINCT session_id) AS sessions, COUNT(*) AS turns,
       COUNT(DISTINCT user_email) AS people, COUNTIF(is_friction_b) AS friction_b,
       COUNTIF(turn_state = 'closed') AS closed_turns, SUM(agent_cost) AS cost, SUM(input_tokens + output_tokens + cache_read_tokens + cache_creation_tokens) AS tokens
FROM {{ds}}.v_turns WHERE {FM} GROUP BY 1, 2, 3 ORDER BY tool, turns DESC""",
    "skills": f"""
WITH e AS (
  SELECT *, CASE WHEN event_name = 'user_prompt' THEN 'command' ELSE 'skill' END AS kind,
         COALESCE(JSON_VALUE(attrs, '$.command_name'), JSON_VALUE(attrs, '$.skill_name'),
                  JSON_VALUE(attrs, '$."skill.name"'), '(name not exported)') AS name
  FROM {{ds}}.v_events
  WHERE DATE(ts, 'America/Sao_Paulo') BETWEEN @start AND @end
    AND (@squad IS NULL OR squad = @squad) AND (@surface IS NULL OR service_name = @surface)
    AND (@email IS NULL OR LOWER(user_email) = LOWER(@email))
    AND ((event_name = 'user_prompt' AND JSON_VALUE(attrs, '$.command_name') IS NOT NULL)
         OR (event_name = 'tool_result' AND JSON_VALUE(attrs, '$.tool_name') = 'Skill')
         OR (event_name = 'api_request' AND JSON_VALUE(attrs, '$."skill.name"') IS NOT NULL)))
-- uses = invocations (slash command typed or Skill tool run); cost = api calls made while that skill was active
SELECT IF(service_name = 'cowork', 'Cowork', 'Claude Code') AS tool, kind, name,
       ANY_VALUE(JSON_VALUE(attrs, '$.command_source')) AS source,
       COUNTIF(event_name != 'api_request') AS uses, COUNT(DISTINCT user_email) AS people,
       COUNT(DISTINCT session_id) AS sessions,
       SUM(IF(event_name = 'api_request', SAFE_CAST(JSON_VALUE(attrs, '$.cost_usd') AS FLOAT64), 0)) AS cost,
       SUM(IF(event_name = 'api_request', IFNULL(SAFE_CAST(JSON_VALUE(attrs, '$.input_tokens') AS INT64), 0)
           + IFNULL(SAFE_CAST(JSON_VALUE(attrs, '$.output_tokens') AS INT64), 0)
           + IFNULL(SAFE_CAST(JSON_VALUE(attrs, '$.cache_read_tokens') AS INT64), 0)
           + IFNULL(SAFE_CAST(JSON_VALUE(attrs, '$.cache_creation_tokens') AS INT64), 0), 0)) AS tokens
FROM e GROUP BY 1, 2, 3 ORDER BY uses DESC, cost DESC""",
    # Spend and token mix per model (all api_requests, agent + overhead).
    "models": f"""
SELECT IFNULL(model, 'unknown') AS model, COUNT(*) AS calls, SUM(cost_usd) AS cost,
       SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens,
       SUM(cache_read_tokens) AS cache_read_tokens, SUM(cache_creation_tokens) AS cache_creation_tokens,
       SUM(input_tokens + output_tokens + cache_read_tokens + cache_creation_tokens) AS tokens
FROM {{ds}}.v_calls
WHERE day BETWEEN @start AND @end AND (@squad IS NULL OR squad = @squad) AND (@surface IS NULL OR surface = @surface)
  AND (@email IS NULL OR LOWER(user_email) = LOWER(@email))
GROUP BY 1 ORDER BY cost DESC""",

    # Spend by hour of day (São Paulo time) over the period, every api_request.
    "hourly": f"""
SELECT EXTRACT(HOUR FROM ts AT TIME ZONE 'America/Sao_Paulo') AS hour, COUNT(*) AS calls, SUM(cost_usd) AS cost,
       SUM(input_tokens + output_tokens + cache_read_tokens + cache_creation_tokens) AS tokens
FROM {{ds}}.v_calls
WHERE day BETWEEN @start AND @end AND (@squad IS NULL OR squad = @squad) AND (@surface IS NULL OR surface = @surface)
  AND (@email IS NULL OR LOWER(user_email) = LOWER(@email)) AND (@model IS NULL OR model = @model)
GROUP BY 1 ORDER BY 1""",
    "domains": f"""
SELECT IF(surface = 'cowork', 'Cowork', 'Claude Code') AS tool, IFNULL(domain, 'untagged') AS domain,
       COUNT(DISTINCT session_id) AS sessions, COUNT(*) AS turns, COUNTIF(is_friction_b) AS friction_b,
       COUNTIF(turn_state = 'closed') AS closed_turns, SUM(agent_cost) AS cost, SUM(input_tokens + output_tokens + cache_read_tokens + cache_creation_tokens) AS tokens
FROM {{ds}}.v_turns WHERE {FM} GROUP BY 1, 2 ORDER BY tool, turns DESC""",

    # 04 Sessions list / one session's turns.
    "sessions": f"""
SELECT session_id, person, user_email, squad, surface, domain, start_ts, end_ts,
       TIMESTAMP_DIFF(end_ts, start_ts, SECOND) AS duration_s, n_turns, n_closed, n_friction_b, n_user_reject,
       n_tool_fail, n_abandoned, n_api_errors, cache_hit, tokens, models, is_live,
       cost_usd, overhead_cost, cold_excess, friction_cost
FROM {{ds}}.v_sessions
WHERE {F} AND (@model IS NULL OR @model IN UNNEST(models)) AND (@session IS NULL OR session_id = @session)
ORDER BY start_ts DESC LIMIT 300""",

    "session_turns": """
SELECT prompt_id, turn_no, start_ts, end_ts, turn_state, category, domain, tone, prompt_length, main_model,
       n_agent_calls, n_tool_calls, n_tool_fail, n_user_reject, n_policy_block, n_api_errors, has_response, has_cold,
       next_gap_s, next_correction_kw, flag_user_reject, flag_tool_fail, flag_fast_reprompt, flag_abandoned,
       fast_reprompt_reason, is_friction_b, is_friction, agent_cost, overhead_cost, cache_read_tokens, input_tokens
FROM {ds}.v_turns WHERE session_id = @session ORDER BY turn_no""",

    # 05 Turns list / one turn + its event timeline (prompt text only while within the 30-day retention).
    "turns": f"""
SELECT prompt_id, session_id, person, user_email, squad, surface, start_ts, turn_state, category, domain, tone, main_model,
       n_agent_calls, n_tool_fail, n_user_reject, has_response, has_cold, is_friction_b, is_friction,
       flag_user_reject, flag_tool_fail, flag_fast_reprompt, flag_abandoned, agent_cost, overhead_cost
FROM {{ds}}.v_turns WHERE {FM} ORDER BY start_ts DESC LIMIT 500""",

    "turn": """
SELECT t.*, (SELECT ANY_VALUE(text) FROM {ds}.raw_texts x WHERE x.prompt_id = t.prompt_id AND x.kind = 'user_prompt') AS prompt_text
FROM {ds}.v_turns t WHERE prompt_id = @prompt""",

    "turn_events": """
SELECT e.ts, e.event_name, e.query_source, e.is_aux,
       JSON_VALUE(e.attrs, '$.tool_name') AS tool_name, JSON_VALUE(e.attrs, '$.decision') AS decision,
       JSON_VALUE(e.attrs, '$.source') AS source, JSON_VALUE(e.attrs, '$.success') AS success,
       JSON_VALUE(e.attrs, '$.model') AS model, SAFE_CAST(JSON_VALUE(e.attrs, '$.duration_ms') AS INT64) AS duration_ms,
       c.cost_usd, c.is_cold, c.cold_reason, a.cold_excess, a.friction, a.useful, a.overhead,
       c.input_tokens, c.output_tokens, c.cache_read_tokens, JSON_VALUE(e.attrs, '$.error') AS error
FROM {ds}.v_events e
LEFT JOIN {ds}.v_calls c ON e.event_name = 'api_request' AND c.prompt_id = e.prompt_id AND c.ts = e.ts
LEFT JOIN {ds}.v_cost_alloc a ON e.event_name = 'api_request' AND a.prompt_id = e.prompt_id AND a.ts = e.ts
WHERE e.prompt_id = @prompt ORDER BY e.ts, e.seq""",

    # 06 Health: tools and MCP connections.
    "tools": """
SELECT JSON_VALUE(attrs, '$.tool_name') AS tool, STARTS_WITH(JSON_VALUE(attrs, '$.tool_name'), 'mcp__') AS is_mcp,
       COUNTIF(event_name = 'tool_result') AS calls,
       COUNTIF(event_name = 'tool_result' AND JSON_VALUE(attrs, '$.success') = 'false') AS fails,
       COUNTIF(event_name = 'tool_decision') AS decisions,
       COUNTIF(event_name = 'tool_decision' AND (JSON_VALUE(attrs, '$.source') = 'user_reject'
               OR (JSON_VALUE(attrs, '$.decision') = 'reject' AND JSON_VALUE(attrs, '$.source') != 'config'))) AS user_rejects,
       APPROX_QUANTILES(IF(event_name = 'tool_result', SAFE_CAST(JSON_VALUE(attrs, '$.duration_ms') AS INT64), NULL), 2)[OFFSET(1)] AS p50_ms
FROM {ds}.v_events
WHERE event_name IN ('tool_result', 'tool_decision')
  AND DATE(ts, 'America/Sao_Paulo') BETWEEN @start AND @end
  AND (@squad IS NULL OR squad = @squad) AND (@surface IS NULL OR service_name = @surface)
  AND (@email IS NULL OR LOWER(user_email) = LOWER(@email))
GROUP BY 1, 2 ORDER BY calls DESC""",

    "mcp": """
SELECT JSON_VALUE(attrs, '$.server_scope') AS scope,  -- Claude Code does not export server names
       JSON_VALUE(attrs, '$.transport_type') AS transport, COUNT(*) AS attempts,
       COUNTIF(JSON_VALUE(attrs, '$.status') = 'failed') AS failures, COUNT(DISTINCT user_email) AS people,
       ARRAY_AGG(DISTINCT JSON_VALUE(attrs, '$.error_code') IGNORE NULLS LIMIT 3) AS error_codes
FROM {ds}.raw_events
WHERE event_name = 'mcp_server_connection'
  AND DATE(ts, 'America/Sao_Paulo') BETWEEN @start AND @end
  AND (@email IS NULL OR LOWER(user_email) = LOWER(@email)) AND (@surface IS NULL OR service_name = @surface)
GROUP BY 1, 2 ORDER BY failures DESC, attempts DESC""",

    # 07 Insights: v1 rules R1, R2a, R2b, R4, R7, R9 (spec §6). One row per firing rule x subject.
    "insights": f"""
WITH t AS (SELECT * FROM {{ds}}.v_turns WHERE {F}),
first_call AS (
  SELECT c.prompt_id, c.user_email, ANY_VALUE(c.person) AS person,
         ARRAY_AGG(c.cache_read_tokens ORDER BY c.ts LIMIT 1)[OFFSET(0)] AS cache_read
  FROM {{ds}}.v_calls c JOIN t USING (prompt_id) WHERE c.is_agent GROUP BY 1, 2),
tl AS (SELECT * FROM ({{QUERIES_TOOLS}}) ),
pd AS (SELECT * FROM {{ds}}.v_person_day WHERE {F})
SELECT 'R1' AS rule, 'context bloat' AS title, person AS subject, user_email,
       APPROX_QUANTILES(cache_read, 2)[OFFSET(1)] AS metric, COUNT(*) AS n,
       'Median context at turn start > 80k tokens: run /compact or /clear between tasks; trim CLAUDE.md.' AS action
FROM first_call GROUP BY person, user_email HAVING metric > 80000
UNION ALL
SELECT 'R2a', 'MCP tool failing', tool, NULL, SAFE_DIVIDE(fails, calls), calls,
       'More than half of calls fail: check the server config/credentials or remove the tool.'
FROM tl WHERE is_mcp AND calls >= 5 AND SAFE_DIVIDE(fails, calls) > 0.5
UNION ALL
SELECT 'R2b', 'MCP connections failing', ANY_VALUE(person), user_email,
       SAFE_DIVIDE(SUM(mcp_failures), SUM(mcp_attempts)), SUM(mcp_attempts),
       'Run /mcp to see which server fails to connect; fix or disable it.'
FROM pd GROUP BY user_email HAVING SUM(mcp_attempts) >= 5 AND SAFE_DIVIDE(SUM(mcp_failures), SUM(mcp_attempts)) > 0.5
UNION ALL
SELECT 'R4', 'permission friction', tool, NULL, SAFE_DIVIDE(user_rejects, decisions), decisions,
       'Users reject this tool often: add allow/deny rules in settings.json so the prompt stops interrupting.'
FROM tl WHERE decisions >= 10 AND SAFE_DIVIDE(user_rejects, decisions) > 0.2
UNION ALL
SELECT 'R7', 'cold starts', ANY_VALUE(person), user_email, SAFE_DIVIDE(SUM(cold_calls), SUM(agent_calls)), SUM(agent_calls),
       'Most calls rebuild the cache: use --continue / --resume and keep sessions under 5 min idle; /compact long ones.'
FROM pd GROUP BY user_email HAVING SUM(agent_calls) >= 10 AND SAFE_DIVIDE(SUM(cold_calls), SUM(agent_calls)) > 0.4
UNION ALL
SELECT 'R9', 'not activated', p.name, p.email, NULL, NULL,
       'In the roster 14+ days with no AI turns: pair them with a squad champion for a first session.'
FROM {{ds}}.people p
WHERE (@squad IS NULL OR p.squad = @squad) AND IFNULL(p.active_from, DATE '2000-01-01') <= DATE_SUB(CURRENT_DATE('America/Sao_Paulo'), INTERVAL 14 DAY)
  AND LOWER(p.email) NOT IN (SELECT LOWER(user_email) FROM pd WHERE turns > 0)
ORDER BY rule, n DESC""",
}

QUERIES["insights"] = QUERIES["insights"].replace("{QUERIES_TOOLS}", QUERIES["tools"])
