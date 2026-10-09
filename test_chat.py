from app.brain import BrainStore
from app.chat import ChatRoom
from app.ingest import Ingestor
from app.ollama_client import OllamaClient, OllamaError, local_embed
from app.prompts import DEFAULT_CHAT_PROMPT


class DummyOllama(OllamaClient):
    def embed(self, text, model=None):
        return local_embed(text)

    def generate(self, prompt, model=None, images=None, system=None, json_mode=False):
        raise OllamaError("offline")


def test_chat_stores_history(tmp_path, monkeypatch):
    monkeypatch.setattr("app.brain.resolve_path", lambda _: tmp_path)
    monkeypatch.setattr("app.ingest.resolve_path", lambda _: tmp_path)
    brain = BrainStore()
    room = ChatRoom(brain, DummyOllama())
    result = room.ask("What is Inverse FVG on EURUSD?")
    assert result["ok"] is True
    assert brain.chat_history()
    assert DEFAULT_CHAT_PROMPT
    brain.close()


def test_forget_memory(tmp_path, monkeypatch):
    monkeypatch.setattr("app.brain.resolve_path", lambda _: tmp_path)
    monkeypatch.setattr("app.ingest.resolve_path", lambda _: tmp_path)
    brain = BrainStore()
    ingestor = Ingestor(brain, DummyOllama())
    memory = ingestor.ingest_text("Test note", "bullish fvg lesson", tags=["note"])
    brain.forget(memory["id"])
    assert all(item["id"] != memory["id"] for item in brain.list_memories())
    brain.close()
