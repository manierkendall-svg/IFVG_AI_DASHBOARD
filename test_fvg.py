from app.demo_market import sample_bullish_setup, sample_fighting_setup, sample_ifvg_setup
from app.fvg import detect_fvgs, rule_decision, summarize_structure


def test_detects_bullish_fvg():
    candles = sample_bullish_setup()["candles"]
    fvgs = detect_fvgs(candles, min_gap_atr=0.05)
    bullish = [z for z in fvgs if z["bias"] == "bullish"]
    assert bullish, "expected at least one bullish FVG"


def test_accepts_aligned_buy():
    payload = sample_bullish_setup()
    fvgs = detect_fvgs(payload["candles"], min_gap_atr=0.05)
    structure = summarize_structure(payload["candles"], fvgs)
    decision = rule_decision(structure, payload, min_confidence=0.5)
    assert decision["action"] == "ACCEPT"
    assert decision["confidence"] >= 0.5


def test_denies_fighting_direction():
    payload = sample_fighting_setup()
    fvgs = detect_fvgs(payload["candles"], min_gap_atr=0.05)
    structure = summarize_structure(payload["candles"], fvgs)
    decision = rule_decision(structure, payload, min_confidence=0.5)
    assert decision["action"] == "DENY"


def test_detects_inverse_fvg():
    payload = sample_ifvg_setup()
    fvgs = detect_fvgs(payload["candles"], min_gap_atr=0.05)
    inverted = [z for z in fvgs if z["kind"] == "IFVG"]
    assert inverted, "expected an Inverse FVG after the gap was reclaimed"
    structure = summarize_structure(payload["candles"], fvgs)
    decision = rule_decision(structure, payload, min_confidence=0.5)
    assert structure["ifvg_count"] >= 1
    assert decision["action"] in {"ACCEPT", "DENY"}
