from __future__ import annotations

from app.config import CONFIG, resolve_path
from app.ingest import Ingestor


CORE_PLAYBOOK = """# FVG and Inverse FVG Trading Brain

This is internalized market memory, not a Q&A sheet. Use it every time a chart or candle stream arrives.

## Fair Value Gap (FVG)
A Fair Value Gap is a three-candle imbalance.
- Bullish FVG: candle 1 high is below candle 3 low. The middle candle is a displacement candle.
- Bearish FVG: candle 1 low is above candle 3 high.
- The untraded gap is inefficiency. Price often returns to fill or react from it.
- Fresh / open FVG is higher quality than a fully filled gap.
- Partial fill into the midpoint (CE) is a common reaction point.
- Do not treat every tiny wick gap as an FVG. Require displacement and a gap relative to ATR.

## Inverse Fair Value Gap (IFVG)
An Inverse FVG is an FVG that fails and is reclaimed in the opposite direction.
- A bullish FVG becomes Inverse when price fully trades through it and closes beyond the opposite side, then the same zone starts acting as resistance.
- A bearish FVG becomes Inverse when price trades up through it and the zone starts acting as support.
- IFVG is a polarity flip: old imbalance becomes opposite-side liquidity magnet / decision zone.
- Inverse FVG is strongest after a liquidity sweep plus displacement through the original gap.

## Accept a trade only when most of these are true
1. Clear displacement created the FVG or IFVG.
2. Proposed direction agrees with the nearest unfilled or inverted zone.
3. Price is reacting at the zone, not blindly mid-range.
4. Higher-timeframe drift does not violently oppose the idea.
5. Invalidation is obvious: opposite side of the zone or swing that created the displacement.
6. If structure is messy (many inverted gaps, overlapping ranges), DENY.

## Deny immediately when
- Direction fights the nearest FVG/IFVG bias.
- The gap is tiny versus ATR.
- The zone is already fully filled and never inverted.
- No screenshot and candles are too few to trust.
- Spread, news, or EA comment indicates a low-quality impulse.
- Confidence is below the dashboard threshold.

## Screenshot reading
When a chart image is present:
- Identify impulse candles (large bodies, little overlap).
- Mark unfilled rectangles between candle 1 and candle 3.
- Note if later candles wicked into the gap (partial) or closed through (inversion).
- Prefer trades where entry is at the unfilled side or IFVG retest, not chasing the close of displacement.

## Memory usage
Any PDF, note, screenshot, or playbook stored in this brain is prior experience.
Recall matching lessons and apply them as if they were the trader's own memory.
Never invent fills that candles do not show.
"""


def seed_core_knowledge(ingestor: Ingestor) -> None:
    knowledge_dir = resolve_path(CONFIG.brain.knowledge_dir)
    playbook = knowledge_dir / "fvg_ifvg_playbook.md"
    if not playbook.exists():
        playbook.write_text(CORE_PLAYBOOK, encoding="utf-8")
    existing = {item["title"].lower() for item in ingestor.brain.list_memories(limit=500)}
    if "fvg and inverse fvg trading brain" not in existing:
        ingestor.ingest_path(playbook, tags=["core", "fvg", "ifvg", "playbook"])
    extra_notes = [
        (
            "Displacement first",
            "Never accept an FVG trade without a displacement candle. "
            "The middle candle of the three-candle pattern must show intent.",
            ["rule", "fvg"],
        ),
        (
            "IFVG polarity flip",
            "Once price closes through an FVG and later retests it from the other side, "
            "treat it as Inverse FVG. Old support becomes resistance and vice versa.",
            ["rule", "ifvg"],
        ),
        (
            "Partial fill CE",
            "The 50 percent level of an open FVG is consequential entry. "
            "A full fill without inversion weakens continuation.",
            ["rule", "fvg"],
        ),
    ]
    for title, content, tags in extra_notes:
        if title.lower() not in existing:
            ingestor.ingest_text(title, content, tags=tags)
