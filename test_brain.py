from pathlib import Path

from app.brain import BrainStore, lexical_score
from app.ollama_client import local_embed


def test_remember_and_recall(tmp_path, monkeypatch):
    monkeypatch.setattr("app.brain.resolve_path", lambda _: Path(tmp_path))
    store = BrainStore()
    store.remember(
        kind="note",
        title="Inverse FVG polarity",
        content="When a bullish FVG is reclaimed from above it becomes IFVG resistance.",
        tags=["ifvg"],
        embedding=local_embed("inverse fvg polarity resistance"),
    )
    hits = store.recall("IFVG polarity flip resistance", embeddings=local_embed("IFVG polarity flip"))
    assert hits
    assert "IFVG" in hits[0]["content"] or "ifvg" in hits[0]["title"].lower() or hits[0]["score"] > 0
    store.close()


def test_lexical_overlap():
    assert lexical_score("bullish fvg gap", "bullish fair value gap imbalance") > 0
