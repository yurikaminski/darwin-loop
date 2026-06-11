import uuid
import time
import json
import hashlib
import re
import collections
from lib.detection.pipeline import FeedbackPipeline

class PrivacyScrubber:
    def __init__(self):
        self.patterns = {
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'phone': r'\b\d{10,15}\b'
        }
    def scrub(self, text: str) -> str:
        for label, pattern in self.patterns.items():
            text = re.sub(pattern, f"<{label.upper()}>", text)
        return text

class DarwinClient:
    def __init__(self, agent_id: str, provider="spacy"):
        self.agent_id = agent_id
        self.session_id = str(uuid.uuid4())
        self.scrubber = PrivacyScrubber()
        self.pipeline = FeedbackPipeline(provider=provider)
        self.context_buffer = collections.deque(maxlen=10)

    def capture_turn(self, role: str, content: str):
        clean_content = self.scrubber.scrub(content)
        self.context_buffer.append({"role": role, "content": clean_content})
        
        # Detecção automática
        result = self.pipeline.process(clean_content)
        if result.get("is_feedback"):
            self.trigger_feedback(result.get("type", "unknown"), clean_content)

    def trigger_feedback(self, feedback_type, context):
        snapshot = {
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "timestamp": time.time(),
            "context_window": list(self.context_buffer),
            "feedback_type": feedback_type,
            "metadata": {"context": context}
        }
        snapshot_json = json.dumps(snapshot, sort_keys=True)
        snapshot_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()
        print(f"DEBUG: Feedback registrado: {feedback_type} | Hash: {snapshot_hash}")
        return {"data": snapshot, "metadata": {"audit_hash": snapshot_hash}}
