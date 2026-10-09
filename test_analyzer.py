from app.analyzer import TradeAnalyzer
from app.brain import BrainStore
from app.demo_market import sample_bullish_setup
from app.ingest import Ingestor
from app.ollama_client import OllamaClient, OllamaError, local_embed
from app.seed import seed_core_knowledge


class DummyOllama(OllamaClient):
    def health(self):
        return {"ok": False, "host": "offline", "models": []}

    def embed(self, text, model=None):
        return local_embed(text)

    def generate(self, prompt, model=None, images=None, system=None, json_mode=False):
        raise OllamaError("ollama offline")


def test_analyzer_falls_back_to_rules(tmp_path, monkeypatch):
    monkeypatch.setattr("app.brain.resolve_path", lambda _: tmp_path)
    monkeypatch.setattr("app.ingest.resolve_path", lambda _: tmp_path)
    monkeypatch.setattr("app.seed.resolve_path", lambda _: tmp_path)
    monkeypatch.setattr("app.analyzer.resolve_path", lambda _: tmp_path)
    brain = BrainStore()
    ollama = DummyOllama()
    ingestor = Ingestor(brain, ollama)
    seed_core_knowledge(ingestor)
    analyzer = TradeAnalyzer(brain, ollama)
    result = analyzer.analyze(sample_bullish_setup())
    assert result["action"] in {"ACCEPT", "DENY"}
    assert result["source"] in {"rules-fallback", "rules"}
    assert result["fvg_count"] >= 1
    brain.close()
