from .triage import TriageFactory
from .classifier import classify_feedback

class FeedbackPipeline:
    def __init__(self, provider="spacy"):
        self.triage = TriageFactory.get(provider)
        
    def process(self, text):
        if self.triage.evaluate(text):
            return classify_feedback(text)
        return {"is_feedback": False}
