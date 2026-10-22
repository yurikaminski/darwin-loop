from otlp import logs_to_rows, metrics_to_rows

S = lambda k, v: {"key": k, "value": {"stringValue": v}}
LOGS = {"resourceLogs": [{"resource": {"attributes": [S("service.name", "claude-code-desktop")]}, "scopeLogs": [{"logRecords": [{
    "timeUnixNano": "1761134400000000000", "body": {"stringValue": "claude_code.user_prompt"},
    "attributes": [S("session.id", "s1"), S("prompt.id", "p1"), S("user.email", "a@b.c"), S("prompt", "oi"),
                   S("prompt_text", "oi"), S("prompt_length", "2"), {"key": "event.sequence", "value": {"intValue": "5"}}]}]}]}]}
METRICS = {"resourceMetrics": [{"resource": {"attributes": [S("service.name", "claude-code")]}, "scopeMetrics": [{"metrics": [{
    "name": "claude_code.cost.usage", "sum": {"dataPoints": [{"asDouble": 0.5, "timeUnixNano": "1761134400000000000",
                                                              "attributes": [S("user.email", "a@b.c"), S("model", "m")]}]}}]}]}]}


def test_logs():
    events, texts = logs_to_rows(LOGS, "now")
    e = events[0]
    assert (e["event_name"], e["prompt_id"], e["seq"], e["service_name"]) == ("user_prompt", "p1", 5, "claude-code-desktop")
    assert "prompt" not in e["attrs"] and "prompt_text" not in e["attrs"]  # text never lands in raw_events
    assert [(t["kind"], t["text"]) for t in texts] == [("prompt", "oi")]


def test_tool_details_scrubbed():
    rec = {"body": {"stringValue": "claude_code.tool_result"}, "attributes": [
        S("tool_name", "Skill"), S("tool_parameters", '{"skill_name": "review", "bash_command": "curl -H secret"}'),
        S("tool_input", '{"cmd": "secret"}'), {"key": "workspace.host_paths", "value": {"arrayValue": {"values": [
            {"stringValue": "/Users/ana/clientes/acme"}]}}}]}
    a = logs_to_rows({"resourceLogs": [{"scopeLogs": [{"logRecords": [rec]}]}]}, "now")[0][0]["attrs"]
    assert a == {"tool_name": "Skill", "skill_name": "review", "dl_project": "acme"}
    rec["attributes"].append(S("vcs.repository.name", "darwin-loop"))
    assert logs_to_rows({"resourceLogs": [{"scopeLogs": [{"logRecords": [rec]}]}]}, "now")[0][0]["attrs"]["dl_project"] == "darwin-loop"


def test_classify():
    from otlp import classify
    c = classify("não é isso, o bug continua")
    assert (c["dl_correction"], c["dl_category"], c["dl_heuristic_version"]) == (True, "bugfix", "kw-5")
    assert classify("crie um endpoint novo")["dl_category"] == "feature"
    assert classify("como funciona o cache?")["dl_category"] == "question"
    assert classify("ESSE TESTE AINDA QUEBRA")["dl_tone"] == "frustration"
    assert classify("valeu, perfeito")["dl_tone"] == "positive"
    assert classify("crie um endpoint novo")["dl_domain"] == "desenvolvimento"
    assert classify("escreva o PRD e as user stories do MVP")["dl_domain"] == "produto"
    assert classify("ajuste o layout da tela e as cores no figma")["dl_domain"] == "design"
    assert classify("rode os testes e2e no playwright")["dl_domain"] == "qa"
    assert classify("bom dia")["dl_domain"] is None
    # spec §4.3 known false positives must not fire the correction cue
    for fp in ("não altere o arquivo X", "precisa de uma decisão", "escrever algo específico", "no caso do docker",
               "isso ainda é crítico", "o address"):
        assert classify(fp)["dl_correction"] is False, fp
    assert logs_to_rows(LOGS, "now")[0][0]["attrs"]["dl_category"] == "other"


def test_redacted_text_dropped():
    LOGS["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"][3] = S("prompt", "<REDACTED>")
    assert logs_to_rows(LOGS, "now")[1] == []


def test_metrics():
    m = metrics_to_rows(METRICS, "now")[0]
    assert (m["name"], m["value"], m["user_email"], m["attrs"]) == ("cost.usage", 0.5, "a@b.c", {"model": "m"})


def test_summary_prompt_truncates():
    import summarize
    texts = [{"kind": "prompt", "turn_no": 1, "text": "x" * 10_000}] * 100
    p = summarize.build_prompt({"cost_usd": 1}, [{"turn_no": 1}], texts, [])
    assert "[…]" in p and "omitido" in p and len(p) < summarize.MAX_TOTAL + 10_000
    assert "sem texto" in summarize.build_prompt({}, [], [], [])


def test_parse_moods_clamps_and_drops_unknown_ids():
    import summarize
    got = summarize.parse_moods('[{"id":"a","mood":5},{"id":"b","mood":-1},{"id":"zz","mood":0},{"id":"c","mood":"2"}]', {"a", "b", "c"})
    assert got == {"a": 2, "b": -1}
