import pytest
from lib.goals.engine import GoalValidator

def test_hard_rule_message_count():
    """Testa se a meta de mensagens é respeitada (Hard Rule)"""
    validator = GoalValidator({"max_messages": 5})
    
    # Simula sessão com 3 mensagens (deve passar)
    assert validator.evaluate({"message_count": 3}) == True
    
    # Simula sessão com 6 mensagens (deve falhar)
    assert validator.evaluate({"message_count": 6}) == False

def test_hard_rule_token_limit():
    """Testa se a meta de tokens é respeitada (Hard Rule)"""
    validator = GoalValidator({"max_tokens": 100})
    
    # Simula sessão com 50 tokens (passa)
    assert validator.evaluate({"total_tokens": 50}) == True
    
    # Simula sessão com 150 tokens (falha)
    assert validator.evaluate({"total_tokens": 150}) == False
