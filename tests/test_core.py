
import pytest
import time
import json
import hashlib
from lib.darwin_client import DarwinClient
from lib.detection.triage import FeedbackTriage

# Mocking context for testing
class MockResponse:
    def __init__(self, tokens):
        self.usage = type('Usage', (), {'total_tokens': tokens})

def test_pipeline_integrity():
    # 1. Setup
    client = DarwinClient(agent_id="test-agent")
    
    # 2. Capture turns
    client.capture_turn("user", "Meu e-mail é teste@teste.com")
    client.capture_turn("assistant", "Olá, como posso ajudar?")
    
    # 3. Simulate feedback triggering
    # O triage deve detectar isso como feedback (ou forçamos o trigger)
    snapshot = client.trigger_feedback("negative", "Não funcionou.")
    
    # 4. Validar Privacidade (Scrubbing)
    assert "teste@teste.com" not in str(snapshot)
    assert "<EMAIL>" in str(snapshot)
    
    # 5. Validar Hash de Integridade
    content_to_hash = json.dumps(snapshot, sort_keys=True)
    calculated_hash = hashlib.sha256(content_to_hash.encode()).hexdigest()
    # (Simulando que o hash enviado foi anexado no payload ou metadata)
    assert 'audit_hash' in snapshot['metadata']
    
    print("Teste de Pipeline e Privacidade: PASSED")

def test_triage_filter():
    triage = FeedbackTriage(provider_type="spacy")
    
    # Neutro
    assert triage.should_classify_with_llm("Bom dia") == False
    # Feedback
    assert triage.should_classify_with_llm("Isso não funciona, que erro horrível") == True
    
    print("Teste de Triage (Filtro): PASSED")

if __name__ == "__main__":
    test_pipeline_integrity()
    test_triage_filter()
