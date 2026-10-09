from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from app.brain import BrainStore
from app.config import CONFIG, resolve_path
from app.fvg import detect_fvgs, rule_decision, summarize_structure
from app.ollama_client import OllamaClient, OllamaError
from app.prompts import DEFAULT_EA_INSTRUCTIONS, DEFAULT_EA_PROMPT
from app.runtime import runtime


DECISION_SCHEMA = """
Return JSON with this exact shape:
{
  "action": "ACCEPT" or "DENY",
  "confidence": number between 0 and 1,
  "reason": "short explanation using FVG / IFVG language",
  "invalidation": "price or structure that kills the idea",
  "targets": ["level or idea"]
}
"""


class TradeAnalyzer:
    def __init__(self, brain: BrainStore, ollama: OllamaClient) -> None:
        self.brain = brain
        self.ollama = ollama
        self.chart_dir = resolve_path(CONFIG.brain.chart_dir)

    def analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.brain.get_setting("paused") == "true":
            result = {
                "action": "DENY",
                "confidence": 0.0,
                "reason": "Brain is paused from the phone dashboard.",
                "source": "control",
                "symbol": payload.get("symbol"),
                "timeframe": payload.get("timeframe"),
            }
            self.brain.save_decision(result)
            return result

        candles = payload.get("candles") or []
        min_conf = float(
            self.brain.get_setting("min_accept_confidence", str(CONFIG.trading.min_accept_confidence))
        )
        fvgs = detect_fvgs(candles, min_gap_atr=CONFIG.trading.fvg_min_gap_atr)
        structure = summarize_structure(candles, fvgs)
        rules = rule_decision(structure, payload, min_conf)
        image_b64 = self._image_b64(payload)
        query = self._query_text(payload, structure, fvgs)
        embedding = self.ollama.embed(query)
        memories = self.brain.recall(query, embeddings=embedding)
        live = runtime.snapshot()
        vision_notes = ""
        llm_decision: dict[str, Any] | None = None
        ollama_error = None
        try:
            if image_b64:
                vision_notes = self.ollama.describe_chart(image_b64, query[:1500])
            llm_decision = self.ollama.decide(
                self._decision_prompt(payload, structure, fvgs, memories, rules, vision_notes, live),
                image_b64=image_b64,
                system=self._ea_system(),
                model=self.brain.get_setting("vision_model") if image_b64 else self.brain.get_setting("text_model"),
            )
        except OllamaError as exc:
            ollama_error = str(exc)

        final = self._merge(rules, llm_decision, min_conf, ollama_error)
        final.update(
            {
                "symbol": payload.get("symbol") or self.brain.get_setting("default_symbol"),
                "timeframe": payload.get("timeframe") or self.brain.get_setting("default_timeframe"),
                "structure": structure,
                "fvg_count": len(fvgs),
                "fvgs": fvgs[-12:],
                "recalled": [
                    {"id": m["id"], "title": m["title"], "score": m.get("score"), "kind": m["kind"]}
                    for m in memories
                ],
                "vision_notes": vision_notes,
                "rules": rules,
                "llm": llm_decision,
                "ticket": payload.get("ticket"),
                "direction": payload.get("direction") or payload.get("side"),
                "entry": payload.get("entry") or payload.get("price") or structure.get("price"),
                "live": {
                    "price": live.get("price"),
                    "profit": live.get("profit"),
                    "session": (live.get("session") or {}).get("label"),
                    "trades_won": live.get("trades_won"),
                    "trades_lost": live.get("trades_lost"),
                    "connected": live.get("connected"),
                },
            }
        )
        stored = self.brain.save_decision(final)
        final["id"] = stored["id"]
        final["created_at"] = stored["created_at"]
        return final

    def _image_b64(self, payload: dict[str, Any]) -> str | None:
        if payload.get("image_base64"):
            return payload["image_base64"]
        path = payload.get("screenshot") or payload.get("image_path")
        if not path:
            return None
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = self.chart_dir / file_path
        if file_path.exists():
            return base64.b64encode(file_path.read_bytes()).decode("ascii")
        return None

    def _query_text(self, payload: dict[str, Any], structure: dict[str, Any], fvgs: list[dict[str, Any]]) -> str:
        nearest = structure.get("nearest") or {}
        return (
            f"{payload.get('symbol')} {payload.get('timeframe')} "
            f"{payload.get('direction') or ''} FVG IFVG {structure.get('trend')} "
            f"{nearest.get('kind', '')} {nearest.get('bias', '')} "
            f"{payload.get('comment', '')} {payload.get('setup', '')}"
        )

    def _decision_prompt(
        self,
        payload: dict[str, Any],
        structure: dict[str, Any],
        fvgs: list[dict[str, Any]],
        memories: list[dict[str, Any]],
        rules: dict[str, Any],
        vision_notes: str,
        live: dict[str, Any] | None = None,
    ) -> str:
        memory_block = "\n\n".join(
            f"- {m['title']} (score {m.get('score')}): {m['content'][:700]}" for m in memories
        ) or "No recalled memories yet."
        fvg_block = json.dumps(fvgs[-8:], indent=2, default=str)
        live = live or {}
        session = (live.get("session") or {}).get("label")
        ea_prompt = self.brain.get_setting("ea_prompt") or DEFAULT_EA_PROMPT
        ea_instructions = self.brain.get_setting("ea_instructions") or DEFAULT_EA_INSTRUCTIONS
        return f"""
{ea_prompt}

{ea_instructions}

Live trade filter request.

Symbol: {payload.get('symbol')}
Timeframe: {payload.get('timeframe')}
Proposed direction: {payload.get('direction') or payload.get('side')}
Entry: {payload.get('entry') or payload.get('price')}
Stop: {payload.get('sl')}
Take profit: {payload.get('tp')}
EA comment: {payload.get('comment') or payload.get('setup') or ''}

Live MT5 account feed:
EA connected: {live.get('connected')}
Current price: {live.get('price')}
Floating P&L: {live.get('profit')}
Balance: {live.get('balance')} Equity: {live.get('equity')}
Open positions: {live.get('open_positions')}
Trades won: {live.get('trades_won')}  Trades lost: {live.get('trades_lost')}
Market session: {session}

Computed market structure:
{json.dumps(structure, indent=2, default=str)}

Detected FVG / IFVG zones:
{fvg_block}

Rule engine suggestion:
{json.dumps(rules, indent=2, default=str)}

Vision notes:
{vision_notes or 'No chart image provided.'}

Memorized trading brain (not Q&A — these are internalized rules, playbooks, and chart lessons):
{memory_block}

Decide ACCEPT or DENY. Prefer DENY unless FVG or Inverse FVG, displacement, and direction agree.
{DECISION_SCHEMA}
""".strip()

    def _merge(
        self,
        rules: dict[str, Any],
        llm: dict[str, Any] | None,
        min_conf: float,
        ollama_error: str | None,
    ) -> dict[str, Any]:
        if not llm:
            reason = "; ".join(rules.get("notes") or [])
            if ollama_error:
                reason = f"{reason} Ollama unavailable: {ollama_error}"
            return {
                "action": rules["action"],
                "confidence": rules["confidence"],
                "reason": reason,
                "source": "rules-fallback",
            }
        # Both must agree to ACCEPT. Either can DENY.
        if rules["action"] == "ACCEPT" and llm["action"] == "ACCEPT":
            confidence = min(rules["confidence"], llm["confidence"])
            action = "ACCEPT" if confidence >= min_conf else "DENY"
            reason = llm.get("reason") or "; ".join(rules.get("notes") or [])
            if action == "DENY":
                reason = f"Confidence {confidence:.2f} below threshold {min_conf:.2f}. {reason}"
            return {
                "action": action,
                "confidence": confidence,
                "reason": reason,
                "invalidation": llm.get("invalidation"),
                "targets": llm.get("targets"),
                "source": "rules+llm",
            }
        deny_reason = llm.get("reason") or "; ".join(rules.get("notes") or [])
        if rules["action"] == "DENY":
            deny_reason = "Rule engine denied: " + "; ".join(rules.get("notes") or [])
        return {
            "action": "DENY",
            "confidence": max(rules["confidence"], llm.get("confidence") or 0),
            "reason": deny_reason,
            "invalidation": llm.get("invalidation"),
            "targets": llm.get("targets"),
            "source": "rules+llm",
        }

    def _ea_system(self) -> str:
        prompt = self.brain.get_setting("ea_prompt") or DEFAULT_EA_PROMPT
        instructions = self.brain.get_setting("ea_instructions") or DEFAULT_EA_INSTRUCTIONS
        return f"{prompt}\n\n{instructions}"
