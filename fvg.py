from __future__ import annotations

from typing import Any


def _atr(candles: list[dict[str, float]], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs: list[float] = []
    for idx in range(1, len(candles)):
        high = float(candles[idx]["high"])
        low = float(candles[idx]["low"])
        prev_close = float(candles[idx - 1]["close"])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    window = trs[-period:] if period else trs
    return sum(window) / len(window) if window else 0.0


def detect_fvgs(candles: list[dict[str, Any]], min_gap_atr: float = 0.15) -> list[dict[str, Any]]:
    """Detect Fair Value Gaps and Inverse FVGs from OHLC candles.

    Bullish FVG: candle[i-2].high < candle[i].low  (gap up, imbalance left)
    Bearish FVG: candle[i-2].low  > candle[i].high (gap down, imbalance left)
    Inverse FVG: an FVG that has been filled by later price action.
    """
    if len(candles) < 3:
        return []
    atr = _atr(candles)
    fvgs: list[dict[str, Any]] = []
    for i in range(2, len(candles)):
        left = candles[i - 2]
        mid = candles[i - 1]
        right = candles[i]
        left_high = float(left["high"])
        left_low = float(left["low"])
        right_high = float(right["high"])
        right_low = float(right["low"])
        mid_body = abs(float(mid["close"]) - float(mid["open"]))

        bullish_gap = right_low - left_high
        bearish_gap = left_low - right_high
        min_gap = atr * min_gap_atr if atr else 0.0

        if bullish_gap > min_gap and bullish_gap > 0:
            zone = {
                "kind": "FVG",
                "bias": "bullish",
                "index": i,
                "time": right.get("time") or right.get("timestamp") or i,
                "top": right_low,
                "bottom": left_high,
                "mid": (right_low + left_high) / 2.0,
                "gap": bullish_gap,
                "impulse": mid_body,
                "filled": False,
                "fill_ratio": 0.0,
                "status": "open",
            }
            _apply_fill_state(zone, candles[i + 1 :])
            fvgs.append(zone)
        elif bearish_gap > min_gap and bearish_gap > 0:
            zone = {
                "kind": "FVG",
                "bias": "bearish",
                "index": i,
                "time": right.get("time") or right.get("timestamp") or i,
                "top": left_low,
                "bottom": right_high,
                "mid": (left_low + right_high) / 2.0,
                "gap": bearish_gap,
                "impulse": mid_body,
                "filled": False,
                "fill_ratio": 0.0,
                "status": "open",
            }
            _apply_fill_state(zone, candles[i + 1 :])
            fvgs.append(zone)
    return fvgs


def _apply_fill_state(zone: dict[str, Any], later: list[dict[str, Any]]) -> None:
    top = float(zone["top"])
    bottom = float(zone["bottom"])
    height = max(top - bottom, 1e-12)
    max_fill = 0.0
    inverted = False
    for candle in later:
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        overlap_top = min(high, top)
        overlap_bottom = max(low, bottom)
        if overlap_top > overlap_bottom:
            fill = (overlap_top - overlap_bottom) / height
            max_fill = max(max_fill, fill)
        if zone["bias"] == "bullish" and close < bottom:
            inverted = True
        if zone["bias"] == "bearish" and close > top:
            inverted = True
    zone["fill_ratio"] = round(min(max_fill, 1.0), 4)
    zone["filled"] = zone["fill_ratio"] >= 0.99
    if inverted and zone["fill_ratio"] >= 0.5:
        zone["kind"] = "IFVG"
        zone["status"] = "inverted"
        zone["bias"] = "bearish" if zone["bias"] == "bullish" else "bullish"
    elif zone["filled"]:
        zone["status"] = "filled"
    elif zone["fill_ratio"] >= 0.5:
        zone["status"] = "partial"
    else:
        zone["status"] = "open"


def summarize_structure(candles: list[dict[str, Any]], fvgs: list[dict[str, Any]]) -> dict[str, Any]:
    if not candles:
        return {
            "price": None,
            "trend": "unknown",
            "open_bullish": 0,
            "open_bearish": 0,
            "ifvg_count": 0,
            "nearest": None,
            "atr": 0.0,
        }
    last = candles[-1]
    price = float(last["close"])
    lookback = candles[-20:] if len(candles) >= 20 else candles
    start = float(lookback[0]["close"])
    if price > start * 1.0008:
        trend = "bullish"
    elif price < start * 0.9992:
        trend = "bearish"
    else:
        trend = "range"
    open_zones = [z for z in fvgs if z["status"] in {"open", "partial"}]
    ifvgs = [z for z in fvgs if z["kind"] == "IFVG"]
    nearest = None
    nearest_dist = None
    for zone in open_zones + ifvgs:
        dist = min(abs(price - zone["top"]), abs(price - zone["bottom"]), abs(price - zone["mid"]))
        if nearest_dist is None or dist < nearest_dist:
            nearest_dist = dist
            nearest = zone
    return {
        "price": price,
        "trend": trend,
        "open_bullish": sum(1 for z in open_zones if z["bias"] == "bullish"),
        "open_bearish": sum(1 for z in open_zones if z["bias"] == "bearish"),
        "ifvg_count": len(ifvgs),
        "nearest": nearest,
        "atr": _atr(candles),
        "bar_count": len(candles),
        "last_time": last.get("time") or last.get("timestamp"),
    }


def rule_decision(
    structure: dict[str, Any],
    proposal: dict[str, Any],
    min_confidence: float,
) -> dict[str, Any]:
    """Deterministic FVG/IFVG gate used alongside the vision LLM."""
    direction = (proposal.get("direction") or proposal.get("side") or "").lower()
    nearest = structure.get("nearest")
    trend = structure.get("trend")
    score = 0.35
    notes: list[str] = []

    if not nearest:
        notes.append("No nearby FVG or IFVG to trade.")
        return {"action": "DENY", "confidence": 0.2, "notes": notes, "source": "rules"}

    if nearest["kind"] == "IFVG":
        score += 0.18
        notes.append(f"Nearest zone is Inverse FVG biased {nearest['bias']}.")
    elif nearest["status"] == "open":
        score += 0.12
        notes.append(f"Open {nearest['bias']} FVG still unfilled.")
    elif nearest["status"] == "partial":
        score += 0.08
        notes.append("FVG is partially filled; wait for a cleaner reaction.")

    if direction in {"buy", "long"} and nearest["bias"] == "bullish":
        score += 0.2
        notes.append("Buy proposal aligns with bullish imbalance.")
    elif direction in {"sell", "short"} and nearest["bias"] == "bearish":
        score += 0.2
        notes.append("Sell proposal aligns with bearish imbalance.")
    elif direction:
        score -= 0.22
        notes.append("Proposed direction fights the nearest imbalance.")

    if trend != "unknown" and (
        (direction in {"buy", "long"} and trend == "bullish")
        or (direction in {"sell", "short"} and trend == "bearish")
    ):
        score += 0.12
        notes.append(f"Higher-timeframe drift is {trend}.")
    elif trend == "range":
        score -= 0.05
        notes.append("Market is ranging; FVG fills are less reliable.")

    if structure.get("ifvg_count", 0) > 2:
        score -= 0.08
        notes.append("Multiple inverted gaps: structure is messy.")

    score = max(0.0, min(score, 0.95))
    action = "ACCEPT" if score >= min_confidence and direction else "DENY"
    if not direction:
        notes.append("EA did not send a direction.")
        action = "DENY"
    return {
        "action": action,
        "confidence": round(score, 3),
        "notes": notes,
        "source": "rules",
        "nearest": nearest,
    }
