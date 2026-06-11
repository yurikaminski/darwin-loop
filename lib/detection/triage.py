import abc
from nltk.sentiment import SentimentIntensityAnalyzer
import spacy

class BaseTriageProvider(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def evaluate(self, text: str) -> bool: pass

class NLTKProvider(BaseTriageProvider):
    def __init__(self): self.sia = SentimentIntensityAnalyzer()
    def evaluate(self, text: str) -> bool:
        score = self.sia.polarity_scores(text)['compound']
        return abs(score) > 0.1

class SpacyProvider(BaseTriageProvider):
    def __init__(self): self.nlp = spacy.load("en_core_web_sm")
    def evaluate(self, text: str) -> bool:
        doc = self.nlp(text)
        # Mais simples: procurar palavras negativas
        return any(token.text.lower() in ['não', 'erro', 'ruim', 'funciona', 'problema'] for token in doc)

class TriageFactory:
    @staticmethod
    def get(provider_type):
        if provider_type == "nltk": return NLTKProvider()
        return SpacyProvider()

class FeedbackTriage:
    def __init__(self, provider_type="spacy"):
        self.provider = TriageFactory.get(provider_type)

    def should_classify_with_llm(self, text):
        return self.provider.evaluate(text)
