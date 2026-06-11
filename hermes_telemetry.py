
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

# Configuração Central
resource = Resource.create({"service.name": "hermes-agent-core"})
trace.set_tracer_provider(TracerProvider(resource=resource))
exporter = OTLPSpanExporter(endpoint="localhost:4317", insecure=True)
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(exporter))
tracer = trace.get_tracer("hermes-instrumentation")

def log_agent_action(action_name, metadata):
    """Função que eu (Hermes) chamarei antes de cada ferramenta"""
    with tracer.start_as_current_span(action_name) as span:
        for k, v in metadata.items():
            span.set_attribute(k, str(v))
        print(f"TELEMETRIA: Registrado '{action_name}'")
