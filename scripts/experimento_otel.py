
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

# Configuração do Resource
resource = Resource.create({"service.name": "hermes-agent-proxy"})

# Configuração do Provider e do Exporter (apontando para o coletor na porta 4318)
trace.set_tracer_provider(TracerProvider(resource=resource))
# Tentar apontar para o Jaeger (porta 4317 é gRPC, 4318 é HTTP).
# O Jaeger all-in-one pode precisar de configuração explícita para aceitar HTTP.
# Vamos tentar gRPC se possível ou corrigir a porta HTTP.
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as OTLPGrpcExporter
otlp_exporter = OTLPGrpcExporter(endpoint="localhost:4317", insecure=True)
span_processor = BatchSpanProcessor(otlp_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)

tracer = trace.get_tracer(__name__)

def trace_my_thought(step_name, attributes):
    with tracer.start_as_current_span(step_name) as span:
        for key, value in attributes.items():
            span.set_attribute(key, value)
        print(f"Telemetria enviada para o nó: {step_name}")

# Teste simples
if __name__ == "__main__":
    trace_my_thought("decisao_de_ferramenta", {"tool": "terminal", "confidence": 0.99})
    trace_my_thought("execucao_de_comando", {"command": "docker-compose up"})
