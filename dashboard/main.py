"""DarwinLoop AI usage dashboard: OTLP/HTTP JSON ingest -> BigQuery, plus a read-only dashboard API."""
import base64
import hashlib
import hmac
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from urllib.parse import parse_qs
from google.cloud import bigquery

from otlp import logs_to_rows, metrics_to_rows
import queries
import summarize

PROJECT = os.environ.get("BQ_PROJECT", "brain003-mvp")
DATASET = os.environ.get("BQ_DATASET", "darwinloop_telemetry")
INGEST_TOKEN = os.environ["INGEST_TOKEN"]
DASH_USER, DASH_PASS = os.environ["DASH_USER"], os.environ["DASH_PASS"]
STATIC = Path(__file__).parent / "static"

bq = bigquery.Client(project=PROJECT)
app = FastAPI(docs_url=None, redoc_url=None)


def _table(name):
    return f"{PROJECT}.{DATASET}.{name}"


def _insert(table, rows, json_cols=()):
    if not rows:
        return
    for r in rows:
        for c in json_cols:
            r[c] = json.dumps(r[c], default=str)
    errors = bq.insert_rows_json(_table(table), rows)
    if errors:
        raise HTTPException(500, f"bigquery insert failed: {errors[:3]}")


def _check_ingest(request):
    got = request.headers.get("authorization", "")
    if not hmac.compare_digest(got, f"Bearer {INGEST_TOKEN}"):
        # fingerprint only, never the header: lets us tell a wrong token from a malformed header
        print(f"ingest 401: len={len(got)} bearer={got.startswith('Bearer ')} sha={hashlib.sha256(got.encode()).hexdigest()[:8]}", flush=True)
        raise HTTPException(401)


SESSION = hmac.new(DASH_PASS.encode(), DASH_USER.encode(), "sha256").hexdigest()  # rotating DASH_PASS logs everyone out


@app.middleware("http")
async def auth(request: Request, call_next):
    # shortcut: one shared credential, upgrade to IAP / Google SSO before wider rollout.
    path = request.url.path
    if path.startswith("/v1/") or path in ("/health", "/login"):
        return await call_next(request)
    basic = "Basic " + base64.b64encode(f"{DASH_USER}:{DASH_PASS}".encode()).decode()
    if hmac.compare_digest(request.cookies.get("dl_session", ""), SESSION) or \
            hmac.compare_digest(request.headers.get("authorization", ""), basic):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "auth required"}, 401)
    return RedirectResponse("/login", 303)


@app.get("/login")
def login_page(error: int = 0):
    return HTMLResponse((STATIC / "login.html").read_text().replace("<!--ERR-->", "<p class=err>Invalid credentials</p>" if error else ""))


@app.post("/login")
async def login(request: Request):
    form = parse_qs((await request.body()).decode())
    ok = hmac.compare_digest(form.get("user", [""])[0], DASH_USER) & hmac.compare_digest(form.get("password", [""])[0], DASH_PASS)
    if not ok:
        return RedirectResponse("/login?error=1", 303)
    r = RedirectResponse("/", 303)
    r.set_cookie("dl_session", SESSION, max_age=7 * 86400, httponly=True, secure=True, samesite="lax")
    return r


@app.get("/health")  # /healthz is reserved by the Cloud Run frontend
def healthz():
    return {"ok": True}


@app.post("/v1/logs")
async def ingest_logs(request: Request):
    _check_ingest(request)
    events, texts = logs_to_rows(await request.json(), datetime.now(timezone.utc).isoformat())
    _insert("raw_events", events, ("attrs", "resource"))
    _insert("raw_texts", texts)
    return {}


@app.post("/v1/metrics")
async def ingest_metrics(request: Request):
    _check_ingest(request)
    _insert("raw_metrics", metrics_to_rows(await request.json(), datetime.now(timezone.utc).isoformat()), ("attrs",))
    return {}


def _values(p):
    # period: explicit from/to (custom range) wins over "last N days"; both are inclusive São Paulo dates.
    try:
        end = date.fromisoformat(p["to"]) if p.get("to") else datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        start = date.fromisoformat(p["from"]) if p.get("from") else end - timedelta(days=min(max(int(p.get("days", 28)), 1), 365))
    except ValueError:
        raise HTTPException(400, "days must be an integer, from/to must be YYYY-MM-DD")
    if start > end or (end - start).days > 366:
        raise HTTPException(400, "from must be <= to and the range at most a year")
    return {"start": start, "end": end, **{k: p.get(k) or None for k in ("squad", "email", "session", "surface", "model", "prompt")}}


def _query(name, values):
    params = [bigquery.ScalarQueryParameter(k, "DATE" if k in ("start", "end") else "STRING", v) for k, v in values.items()]
    sql = queries.QUERIES[name].format(ds=f"`{PROJECT}.{DATASET}`")
    return sql, [dict(r) for r in bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()]


@app.post("/api/session_summary")
def session_summary(request: Request):
    """Executive summary of one session by a cheap Gemini on Vertex AI. Not stored: it derives from prompt text (30-day)."""
    values = _values(request.query_params)
    if not values["session"]:
        raise HTTPException(400, "session is required")
    values["email"] = None
    s = _query("sessions", values)[1]
    if not s:
        raise HTTPException(404, "session not found in this period")
    turns, texts, tools = (_query(q, values)[1] for q in ("session_turns", "session_texts", "session_tools"))
    key = (values["session"], len(turns), len(texts))
    if key not in _summaries:
        _summaries[key] = summarize.summarize(s[0], turns, texts, tools)
    return {"summary": _summaries[key], "model": summarize.MODEL, "n_texts": len(texts)}


@app.post("/api/mood")
def score_mood(request: Request):
    """AI mood of up to 40 closed, unscored turns in the filtered period; the UI repeats until scored == 0."""
    todo = _query("mood_todo", _values(request.query_params))[1]
    if not todo:
        return {"scored": 0}
    scores, sess = summarize.moods(todo), {t["prompt_id"]: t["session_id"] for t in todo}
    now = datetime.now(timezone.utc).isoformat()
    _insert("turn_mood", [{"prompt_id": k, "session_id": sess[k], "mood": v, "model": summarize.MODEL, "scored_at": now} for k, v in scores.items()])
    return {"scored": len(scores)}


_summaries = {}  # shortcut: per-instance memory cache, lost on restart; move to a 30-day table if Gemini cost matters


EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
SQUAD = re.compile(r"[\w .&/+-]{1,40}")


def _assignment(body):
    email, squad = str(body.get("email") or "").strip().lower(), str(body.get("squad") or "").strip() or None
    if len(email) > 254 or not EMAIL.fullmatch(email):
        raise HTTPException(400, "invalid email")
    if squad and not SQUAD.fullmatch(squad):
        raise HTTPException(400, "squad: 1-40 letters, digits, space or . & / + -")
    return email, squad


@app.post("/api/people")
async def assign_squad(request: Request):
    """Admin sets (or clears, with an empty squad) the squad of one person. Views read people live, so every card follows."""
    # shortcut: anyone with the shared dashboard password can edit squads; restrict to admins once IAP / SSO lands.
    email, squad = _assignment(await request.json())
    # DML, not streaming inserts: streamed rows would block this MERGE for ~30 min.
    sql = f"""MERGE `{_table('people')}` p USING (SELECT @email AS email) s ON LOWER(p.email) = s.email
WHEN MATCHED THEN UPDATE SET squad = @squad
WHEN NOT MATCHED AND @squad IS NOT NULL THEN INSERT (email, squad, active_from) VALUES (@email, @squad, CURRENT_DATE('America/Sao_Paulo'))"""
    params = [bigquery.ScalarQueryParameter("email", "STRING", email), bigquery.ScalarQueryParameter("squad", "STRING", squad)]
    bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
    return {"email": email, "squad": squad}


@app.get("/api/{name}")
def api(name: str, request: Request):
    if name not in queries.QUERIES:
        raise HTTPException(404)
    values = _values(request.query_params)
    sql, rows = _query(name, values)
    return {"rows": rows, "sql": sql, "params": values, "n": len(rows)}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
