"""Flatten OTLP/HTTP JSON payloads from Claude Code into BigQuery rows."""
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import PurePath

TEXT_KEYS = {"prompt": "prompt", "prompt_text": None, "response": "response"}  # None = duplicate, dropped
DETAIL_KEYS = ("tool_input", "full_command", "bash_command", "diff", "file_path")  # commands, paths, file contents
KEEP_PARAMS = ("skill_name", "mcp_server_name", "mcp_tool_name")
IDENTITY = {"session.id": "session_id", "prompt.id": "prompt_id", "user.id": "user_id",
            "user.email": "user_email", "organization.id": "org_id"}


# shortcut: keyword heuristics (pt/en, spec v5 §4.3), upgrade to an LLM judge when lib/detection/classify_feedback is real.
HEURISTIC_VERSION = "kw-5"  # kw-5: adds dl_domain; kw-4: correction cue no longer feeds fast_reprompt (PM must_fix)
CATEGORIES = [
    ("bugfix", r"\b(fix(es|ed|ing)?|bugs?|erros?|errors?|quebr\w*|falh\w*|traceback|exceptions?|stack ?trace|broken|crash\w*)\b"
               r"|\bnão (está )?funciona\w*|\bdoesn'?t work\b"),
    ("test", r"\b(tests?|testes?|testar|testing|pytest|jest|vitest|coverage|cobertura|specs?|unit ?tests?)\b"),
    ("refactor", r"\b(refactor\w*|refator\w*|simplif\w*|clean ?up|limpar?|renome\w*|rename\w*|extract\w*|extrair?)\b"),
    ("review", r"\b(review\w*|revis[aeã]\w*|code ?review|audit\w*)\b"),
    ("ops", r"\b(commit\w*|push|merge\w*|deploy\w*|docker\w*|git|prs?|pull request|ci|cd|pipelines?|gcloud|terraform|kubectl|helm)\b"),
    ("docs", r"\b(readme|docs?|documenta\w*|document(ation)?|changelog|docstrings?|coment[aá]rios?|comments?)\b"),
    ("feature", r"\b(add|adicion\w*|implement\w*|cri[ae]r?|criei|create|build|nov[ao]s?|new|feature)\b"),
    ("question", r"\?\s*$|^(como|o que|por ?que|qual|quais|why|what|how|explain|explica\w*)\b"),
]
# Work domain of a prompt: the domain with the most keyword hits wins, ties go to the earlier entry.
DOMAINS = [
    ("qa", r"\b(qa|tests?|testes?|testar|testing|e2e|playwright|cypress|selenium|regress\w*|homolog\w*|valida\w*|reproduz\w*|repro|test ?cases?|casos? de teste|cenários?|coverage|cobertura)\b"),
    ("design", r"\b(design|ui|ux|figma|layout|css|tailwind|cor(es)?|colou?rs?|fontes?|fonts?|tipogra\w*|typograph\w*|wireframes?|mockups?|prot[oó]tip\w*|prototyp\w*|visual|ícones?|icons?|telas?|screens?|espaçamento|spacing|responsiv\w*|acessibilidade|accessibility)\b"),
    ("produto", r"\b(prd|produto|product|requisitos?|requirements?|user stor\w*|hist[oó]rias?|roadmap|backlog|[ée]picos?|epics?|personas?|métricas?|metrics?|kpis?|okrs?|mvp|prioriz\w*|prioriti\w*|discovery|stakeholders?|clientes?|customers?|jornada|journey|escopo|scope|pricing|preç\w*|mercado|market|concorren\w*|competitors?)\b"),
    ("desenvolvimento", r"\b(c[oó]digo|code|fun[çc][ãa]o|function|api|endpoints?|deploy\w*|refator\w*|refactor\w*|bugs?|fix\w*|implement\w*|python|sql|query|git|commit\w*|docker\w*|scripts?|database|banco de dados|backend|frontend|class(e|es)?|compil\w*|build|prs?|merge\w*|lint\w*|migra\w*|schema)\b"),
]
CORRECTION = re.compile(
    r"^(não|nao|no|nope)\s*[,.!;:]|\b(não|nao) (é|era|foi) (isso|assim)\b|\bisso não\b|\bnot (that|this|what)\b|\bthat'?s not\b"
    r"|\b(errad[oa]|wrong|incorret[oa]|incorrect)\b"
    r"|\b(de novo|again|outra vez)\b|\bainda (não|nao|está|esta|dá|da|continua)\b|\bstill (not|broken|failing|wrong)\b"
    r"|\bcontinua (dando|com|quebr\w*|falh\w*)\b|\b(na verdade|actually|instead|em vez|ao invés)\b"
    r"|\b(desfa[zç]\w*|undo|revert\w*|volta[r]? (atrás|o que))\b")
POSITIVE = re.compile(r"\b(obrigad[oa]|valeu|thanks?|perfeito|perfect|ótimo|great|boa)\b")


def classify(text):
    t = unicodedata.normalize("NFC", text).lower().strip()
    category = next((c for c, rx in CATEGORIES if re.search(rx, t)), "other")
    letters = [c for c in text if c.isalpha()]
    upper = len(letters) >= 10 and sum(c.isupper() for c in letters) / len(letters) >= 0.5
    tone = "frustration" if "!!" in t or upper else "positive" if POSITIVE.search(t) else "neutral"
    hits = [len(re.findall(rx, t)) for _, rx in DOMAINS]
    domain = DOMAINS[hits.index(max(hits))][0] if max(hits) else None
    return {"dl_category": category, "dl_domain": domain, "dl_tone": tone,
            "dl_correction": bool(CORRECTION.search(" ".join(t.split()[:5]))),  # first 5 tokens only
            "dl_words": len(t.split()), "dl_has_code": "```" in t, "dl_heuristic_version": HEURISTIC_VERSION}


def _val(v):
    if not v:
        return None
    k, x = next(iter(v.items()))
    if k == "intValue":
        return int(x)
    if k == "arrayValue":
        return [_val(i) for i in x.get("values", [])]
    if k == "kvlistValue":
        return _attrs(x.get("values"))
    return x


def _attrs(items):
    return {a["key"]: _val(a.get("value")) for a in items or []}


def _ts(nanos):
    return datetime.fromtimestamp(int(nanos) / 1e9, timezone.utc).isoformat() if nanos else None


def _common(a, res):
    row = {col: a.pop(key, None) for key, col in IDENTITY.items()}
    row["service_name"] = res.get("service.name")
    row["team"] = a.get("team") or res.get("team")
    return row


def _json(v):
    if not isinstance(v, str):
        return v
    try:
        return json.loads(v)
    except ValueError:
        return v


def _scrub_details(a, res):
    """Tool details (OTEL_LOG_TOOL_DETAILS / Cowork toolDetails) keep only names; project = repo, else folder name."""
    params = _json(a.pop("tool_parameters", None))
    if isinstance(params, dict):
        a.update({k: params[k] for k in KEEP_PARAMS if params.get(k)})
    for k in DETAIL_KEYS:
        a.pop(k, None)
    paths = _json(a.pop("workspace.host_paths", None)) or []  # full paths dropped, only the folder name survives
    paths = [paths] if isinstance(paths, str) else paths
    project = a.get("vcs.repository.name") or res.get("vcs.repository.name") or (PurePath(paths[0]).name if paths else None)
    if project:
        a["dl_project"] = project


def logs_to_rows(payload, received_at):
    """Returns (event_rows, text_rows). Text is split out so it can expire after 30 days."""
    events, texts = [], []
    for rl in payload.get("resourceLogs", []):
        res = _attrs(rl.get("resource", {}).get("attributes"))
        for sl in rl.get("scopeLogs", []):
            for lr in sl.get("logRecords", []):
                a = _attrs(lr.get("attributes"))
                row = _common(a, res)
                ts = a.pop("event.timestamp", None) or _ts(lr.get("timeUnixNano") or lr.get("observedTimeUnixNano"))
                seq = a.pop("event.sequence", None)
                for key, kind in TEXT_KEYS.items():
                    text = a.pop(key, None)
                    if kind and text and text != "<REDACTED>":
                        if kind == "prompt":
                            a.update(classify(text))  # derived fields live in raw_events, survive text expiry
                        texts.append({"ts": ts, "session_id": row["session_id"], "prompt_id": row["prompt_id"],
                                      "message_uuid": a.get("message.uuid"), "user_email": row["user_email"],
                                      "kind": kind, "text": text})
                _scrub_details(a, res)
                name = _val(lr.get("body")) or a.get("event.name") or ""
                events.append({**row, "ts": ts, "received_at": received_at, "seq": seq,
                               "event_name": name.removeprefix("claude_code."),
                               "service_version": res.get("service.version"), "attrs": a, "resource": res})
    return events, texts


def metrics_to_rows(payload, received_at):
    rows = []
    for rm in payload.get("resourceMetrics", []):
        res = _attrs(rm.get("resource", {}).get("attributes"))
        for sm in rm.get("scopeMetrics", []):
            for m in sm.get("metrics", []):
                data = next((v for v in m.values() if isinstance(v, dict) and "dataPoints" in v), {})
                for dp in data.get("dataPoints", []):
                    a = _attrs(dp.get("attributes"))
                    row = _common(a, res)
                    row.pop("prompt_id"), row.pop("user_id"), row.pop("org_id")
                    value = dp.get("asDouble", dp.get("asInt"))
                    rows.append({**row, "ts": _ts(dp.get("timeUnixNano")), "received_at": received_at,
                                 "name": m["name"].removeprefix("claude_code."),
                                 "value": float(value) if value is not None else None, "attrs": a})
    return rows
