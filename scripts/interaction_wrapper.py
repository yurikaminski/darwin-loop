
import os
from lib.telemetry.sdk import log_agent_action

def process_user_interaction(user_input, project_name="darwin-loop"):
    """
    Wrapper que simula o hook de entrada/saída para telemetria.
    """
    # 1. Hook de Entrada
    log_agent_action("interacao_usuario_inicio", {
        "projeto": project_name,
        "input_snippet": user_input[:50]
    })
    
    # --- Aqui entraria a lógica de processamento do Hermes ---
    print(f"Processando: {user_input}")
    
    # 2. Hook de Saída
    log_agent_action("interacao_usuario_fim", {
        "projeto": project_name,
        "status": "sucesso"
    })

if __name__ == "__main__":
    process_user_interaction("Como otimizar meu agente?")
