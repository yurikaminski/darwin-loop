from dataclasses import dataclass
from lib.metrics.engine import FEREngine, Metrics

@dataclass
class Signal:
    weight: float

@dataclass
class Episode:
    tokens: int
    negative_signals: list[Signal]
    positive_signals: list[Signal]

class MockDataStore:
    def __init__(self):
        self.episodes = []

    def get_recent_episodes(self, agent_id, days):
        return self.episodes

    def add_episode(self, episode):
        self.episodes.append(episode)

# Teste
if __name__ == "__main__":
    store = MockDataStore()
    # Simula 1000 tokens com 2 feedbacks negativos (peso 3) e 5 positivos (peso 1)
    store.add_episode(Episode(1000, [Signal(3.0), Signal(3.0)], [Signal(1.0)]*5))
    
    engine = FEREngine(store)
    metrics = engine.calculate_metrics("test-agent")
    
    print(f"Métricas Calculadas: {metrics}")
