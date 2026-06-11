import sys
import os

# Adiciona a pasta lib ao caminho de busca do Python
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.telemetry.sdk import log_agent_action

log_agent_action("teste_de_integracao", {"status": "sucesso", "projeto": "darwin-loop"})
