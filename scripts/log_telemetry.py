
import argparse
import json
import os
import time
import uuid
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

# Configuração simples
resource = Resource.create({"service.name": "hermes-agent-proxy"})
provider = TracerProvider(resource=resource)
exporter = OTLPSpanExporter(endpoint="localhost:4317", insecure=True)
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

# Gerencia o trace_id persistente
TRACE_FILE = "/tmp/hermes_current_trace.json"

def get_or_create_trace_id():
    if os.path.exists(TRACE_FILE):
        with open(TRACE_FILE, "r") as f:
            return json.load(f)["trace_id"]
    new_id = uuid.uuid4().hex
    with open(TRACE_FILE, "w") as f:
        json.dump({"trace_id": new_id}, f)
    return new_id

def log_action(action, msg):
    trace_id = get_or_create_trace_id()
    # Log estruturado
    with tracer.start_as_current_span(action) as span:
        span.set_attribute("message", msg)
        span.set_attribute("trace_id", trace_id)
        print(f"Telemetria [{action}] registrada para trace {trace_id}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True)
    parser.add_argument("--msg", default="")
    args = parser.parse_args()

    if args.action == "fim":
        if os.path.exists(TRACE_FILE):
            os.remove(TRACE_FILE)
    
    log_action(args.action, args.msg)
