from __future__ import annotations

from typing import Any


def sample_bullish_setup() -> dict[str, Any]:
    candles: list[dict[str, Any]] = []
    price = 1.0800
    for i in range(40):
        drift = 0.00012 if i < 28 else 0.00035
        open_px = price
        close_px = price + drift
        high = max(open_px, close_px) + 0.00008
        low = min(open_px, close_px) - 0.00006
        candles.append(
            {
                "time": 1700000000 + i * 900,
                "open": round(open_px, 5),
                "high": round(high, 5),
                "low": round(low, 5),
                "close": round(close_px, 5),
                "volume": 1000 + i,
            }
        )
        price = close_px

    # Three-candle bullish FVG: left high well below right low.
    left_open = price
    candles.append(
        {
            "time": 1700000000 + 40 * 900,
            "open": round(left_open, 5),
            "high": round(left_open + 0.00010, 5),
            "low": round(left_open - 0.00010, 5),
            "close": round(left_open + 0.00004, 5),
            "volume": 1200,
        }
    )
    mid_open = left_open + 0.00004
    candles.append(
        {
            "time": 1700000000 + 41 * 900,
            "open": round(mid_open, 5),
            "high": round(mid_open + 0.00240, 5),
            "low": round(mid_open - 0.00005, 5),
            "close": round(mid_open + 0.00220, 5),
            "volume": 3400,
        }
    )
    right_open = mid_open + 0.00220
    candles.append(
        {
            "time": 1700000000 + 42 * 900,
            "open": round(right_open, 5),
            "high": round(right_open + 0.00030, 5),
            "low": round(right_open - 0.00008, 5),
            "close": round(right_open + 0.00018, 5),
            "volume": 1600,
        }
    )
    last = candles[-1]["close"]
    return {
        "symbol": "EURUSD",
        "timeframe": "M15",
        "direction": "buy",
        "entry": last,
        "comment": "demo bullish FVG displacement",
        "candles": candles,
    }


def sample_fighting_setup() -> dict[str, Any]:
    payload = sample_bullish_setup()
    payload["direction"] = "sell"
    payload["comment"] = "demo sell into bullish FVG"
    return payload


def sample_ifvg_setup() -> dict[str, Any]:
    payload = sample_bullish_setup()
    candles = list(payload["candles"])
    last = candles[-1]
    price = float(last["close"])
    fvg_bottom = float(candles[-3]["high"])
    for i in range(6):
        open_px = price
        close_px = price - 0.00090
        candles.append(
            {
                "time": int(last["time"]) + (i + 1) * 900,
                "open": round(open_px, 5),
                "high": round(max(open_px, close_px) + 0.00005, 5),
                "low": round(min(open_px, close_px, fvg_bottom - 0.00040) - 0.00010, 5),
                "close": round(close_px, 5),
                "volume": 2000,
            }
        )
        price = close_px
    payload["candles"] = candles
    payload["direction"] = "sell"
    payload["comment"] = "demo inverse FVG after failed bullish gap"
    payload["entry"] = price
    return payload
