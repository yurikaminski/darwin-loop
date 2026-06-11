
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as OTLPGrpcExporter
from opentelemetry.sdk.resources import Resource

# Configuração centralizada para o SDK de telemetria
resource = Resource.create({"service.name": "darwin-loop-agent"})
tracer_provider = TracerProvider(resource=resource)
otlp_exporter = OTLPGrpcExporter(endpoint="localhost:4317", insecure=True)
span_processor = BatchSpanProcessor(otlp_exporter)
tracer_provider.add_span_processor(span_processor)
trace.set_tracer_provider(tracer_provider)

tracer = trace.get_tracer("darwin-loop.telemetry")

def log_agent_action(step_name, attributes):
    with tracer.start_as_current_span(step_name) as span:
        for key, value in attributes.items():
            span.set_attribute(key, value)
        print(f"Telemetria enviada para o nó: {step_name}")
