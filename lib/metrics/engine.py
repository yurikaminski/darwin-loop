from dataclasses import dataclass
from datetime import datetime, timedelta
import collections

@dataclass
class Metrics:
    nfr: float = 0.0
    pfr: float = 0.0
    ainps: float = 0.0
    w_nfr: float = 0.0

class FEREngine:
    def __init__(self, data_store):
        self.data_store = data_store

    def calculate_metrics(self, agent_id, window_days=7):
        episodes = self.data_store.get_recent_episodes(agent_id, days=window_days)
        if not episodes:
            return Metrics()
        
        total_tokens = sum(e.tokens for e in episodes)
        if total_tokens == 0: return Metrics()

        neg_weight = sum(s.weight for e in episodes for s in e.negative_signals)
        pos_weight = sum(s.weight for e in episodes for s in e.positive_signals)
        
        # FR-F1: NFR = neg_weight / tokens
        nfr = neg_weight / total_tokens
        # FR-F2: PFR = pos_weight / tokens
        pfr = pos_weight / total_tokens
        # FR-F3: AINPS = (pos - neg) / tokens
        ainps = (pos_weight - neg_weight) / total_tokens
        
        return Metrics(nfr=nfr, pfr=pfr, ainps=ainps)
