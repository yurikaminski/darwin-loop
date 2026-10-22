"""Flatten an otlp_receiver.py dump into one line per event/metric point, hiding identity attrs.

Usage: python3 scripts/otlp_view.py otlp_dump.jsonl
"""
import json
import sys

COMMON = {"user.id", "session.id", "organization.id", "user.email", "user.account_uuid", "user.account_id",
          "terminal.type", "event.timestamp", "deployment.environment", "team"}


def val(v):
    return next(iter(v.values()), None) if v else None


def attrs(items):
    return {a["key"]: val(a["value"]) for a in items or []}


for line in open(sys.argv[1]):
    rec = json.loads(line)["payload"]
    for rl in rec.get("resourceLogs", []):
        for sl in rl["scopeLogs"]:
            for lr in sl["logRecords"]:
                a = attrs(lr["attributes"])
                print("EVENT ", val(lr["body"]), {k: v for k, v in a.items() if k not in COMMON})
    for rm in rec.get("resourceMetrics", []):
        for sm in rm["scopeMetrics"]:
            for m in sm["metrics"]:
                for dp in next(iter(v for k, v in m.items() if isinstance(v, dict) and "dataPoints" in v))["dataPoints"]:
                    a = attrs(dp["attributes"])
                    n = dp.get("asDouble", dp.get("asInt"))
                    print("METRIC", m["name"], n, {k: v for k, v in a.items() if k not in COMMON})
