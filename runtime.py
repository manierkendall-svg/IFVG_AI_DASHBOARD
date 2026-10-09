from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any


EA_TIMEOUT_SEC = 35


def market_session(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    hour = now.hour
    active: list[str] = []
    if hour >= 21 or hour < 6:
        active.append("Sydney")
    if 0 <= hour < 9:
        active.append("Tokyo")
    if 7 <= hour < 16:
        active.append("London")
    if 12 <= hour < 21:
        active.append("New York")
    primary = active[-1] if active else "Off-hours"
    return {
        "utc_hour": hour,
        "utc": now.strftime("%H:%M UTC"),
        "active": active,
        "primary": primary,
        "label": " / ".join(active) if active else "Off-hours",
    }


class Runtime:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.heartbeat: dict[str, Any] = {}
        self.last_command_result: dict[str, Any] = {}
        self.last_pong_at: float = 0.0

    def update_heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = market_session()
        snapshot = {
            **payload,
            "received_at": time.time(),
            "session": session,
            "price": payload.get("price") or payload.get("bid") or payload.get("ask"),
        }
        with self._lock:
            self.heartbeat = snapshot
            if payload.get("pong") or payload.get("last_command") == "ping":
                self.last_pong_at = time.time()
        return snapshot

    def connected(self) -> bool:
        with self._lock:
            stamp = self.heartbeat.get("received_at")
        return bool(stamp and (time.time() - stamp) < EA_TIMEOUT_SEC)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            hb = dict(self.heartbeat)
            pong = self.last_pong_at
            result = dict(self.last_command_result)
        connected = bool(hb.get("received_at") and (time.time() - hb["received_at"]) < EA_TIMEOUT_SEC)
        age = None
        if hb.get("received_at"):
            age = round(time.time() - hb["received_at"], 1)
        return {
            "connected": connected,
            "status": "CONNECTED" if connected else "NOT CONNECTED",
            "age_sec": age,
            "symbol": hb.get("symbol"),
            "timeframe": hb.get("timeframe"),
            "bid": _num(hb.get("bid")),
            "ask": _num(hb.get("ask")),
            "price": _num(hb.get("price") or hb.get("bid")),
            "balance": _num(hb.get("balance")),
            "equity": _num(hb.get("equity")),
            "profit": _num(hb.get("profit") or hb.get("pnl") or hb.get("floating_pnl")),
            "margin": _num(hb.get("margin")),
            "open_positions": int(hb.get("open_positions") or hb.get("positions") or 0),
            "trades_won": int(hb.get("trades_won") or hb.get("wins") or 0),
            "trades_lost": int(hb.get("trades_lost") or hb.get("losses") or 0),
            "session": hb.get("session") or market_session(),
            "account": hb.get("account"),
            "currency": hb.get("currency") or "USD",
            "last_pong_at": pong,
            "last_command_result": result,
            "raw": hb,
        }

    def set_command_result(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self.last_command_result = {**payload, "received_at": time.time()}
            if str(payload.get("action") or payload.get("command") or "") == "ping":
                self.last_pong_at = time.time()


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


runtime = Runtime()
