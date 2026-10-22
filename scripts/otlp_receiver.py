"""Minimal OTLP/HTTP JSON receiver: appends every payload to a JSONL file for inspection.

Usage: python3 scripts/otlp_receiver.py [port] [out.jsonl]
Point clients at it with OTEL_EXPORTER_OTLP_PROTOCOL=http/json.
"""
import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4318
OUT = sys.argv[2] if len(sys.argv) > 2 else "otlp_dump.jsonl"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            payload = json.loads(body)
        except ValueError:
            # shortcut: protobuf bodies are stored as size only, switch the client to http/json to see them
            payload = {"_non_json_bytes": len(body), "_content_type": self.headers.get("Content-Type")}
        with open(OUT, "a") as f:
            f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "path": self.path, "payload": payload}) + "\n")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, fmt, *args):
        print(self.path, file=sys.stderr)


if __name__ == "__main__":
    print(f"listening on :{PORT}, writing {OUT}", file=sys.stderr)
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
