from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseOptimizerAgent(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def evolve(self, feedback_batch: list) -> Dict[str, Any]:
        """Process feedback and return optimized configuration (prompt or weights)."""
        pass
