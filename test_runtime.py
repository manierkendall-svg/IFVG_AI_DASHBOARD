from app.brain import BrainStore
from app.runtime import Runtime, market_session


def test_market_session_has_label():
    session = market_session()
    assert session["label"]
    assert "utc" in session


def test_runtime_connects_on_heartbeat():
    rt = Runtime()
    assert rt.connected() is False
    rt.update_heartbeat({"symbol": "EURUSD", "bid": 1.08, "profit": 12.5, "trades_won": 3, "trades_lost": 1})
    snap = rt.snapshot()
    assert snap["connected"] is True
    assert snap["status"] == "CONNECTED"
    assert snap["trades_won"] == 3
    assert snap["profit"] == 12.5


def test_enqueue_command(tmp_path, monkeypatch):
    monkeypatch.setattr("app.brain.resolve_path", lambda _: tmp_path)
    store = BrainStore()
    cmd = store.enqueue_command("ping", {"from": "dashboard"})
    queued = store.next_commands()
    assert queued and queued[0]["id"] == cmd["id"]
    acked = store.ack_command(cmd["id"], result={"ok": True})
    assert acked["status"] == "done"
    assert store.next_commands() == []
    store.close()
