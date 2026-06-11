import time
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, BatchSpanProcessor

# 1. Configurar o provedor de traces para exportar para o console (fácil visualização)
provider = TracerProvider()
processor = BatchSpanProcessor(ConsoleSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)

# 2. Experimento: Simulação de Agente de IA com instrumentação semântica
def agente_darwin_loop():
    with tracer.start_as_current_span("agente_darwin_loop") as span:
        span.set_attribute("projeto", "Darwin Loop")
        span.set_attribute("versao_algoritmo", "0.1.0-experimental")
        
        print("Agente iniciando raciocínio...")
        
        # Simula nó de análise
        with tracer.start_as_current_span("nó_análise") as sub_span:
            time.sleep(0.5)
            sub_span.set_attribute("status", "análise_concluída")
            print(" - Análise de contexto feita.")
            
        # Simula nó de decisão
        with tracer.start_as_current_span("nó_decisão") as sub_span:
            time.sleep(0.3)
            sub_span.set_attribute("confiança_do_modelo", 0.95)
            print(" - Decisão tomada.")

if __name__ == "__main__":
    agente_darwin_loop()
    # Espera um pouco para o exportador processar
    time.sleep(1)
