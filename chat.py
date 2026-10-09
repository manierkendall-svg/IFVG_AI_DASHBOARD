from __future__ import annotations

from typing import Any

from app.brain import BrainStore
from app.ollama_client import OllamaClient, OllamaError
from app.prompts import DEFAULT_CHAT_INSTRUCTIONS, DEFAULT_CHAT_PROMPT
from app.runtime import runtime


class ChatRoom:
    def __init__(self, brain: BrainStore, ollama: OllamaClient) -> None:
        self.brain = brain
        self.ollama = ollama

    def ask(self, message: str) -> dict[str, Any]:
        message = (message or "").strip()
        if not message:
            raise ValueError("Empty message")
        self.brain.add_chat("user", message)
        live = runtime.snapshot()
        memories = self.brain.recall(message, embeddings=self.ollama.embed(message), limit=8)
        history = self.brain.chat_history(12)
        prompt = self.brain.get_setting("chat_prompt") or DEFAULT_CHAT_PROMPT
        instructions = self.brain.get_setting("chat_instructions") or DEFAULT_CHAT_INSTRUCTIONS
        model = self.brain.get_setting("text_model")
        memory_block = "\n".join(
            f"- {item['title']}: {item['content'][:500]}" for item in memories
        ) or "No library documents recalled."
        hist_block = "\n".join(f"{item['role']}: {item['content']}" for item in history[-10:])
        session = (live.get("session") or {}).get("label")
        user_prompt = f"""{prompt}

{instructions}

Live MT5 feed:
connected={live.get('connected')} symbol={live.get('symbol')} price={live.get('price')}
P&L={live.get('profit')} equity={live.get('equity')} session={session}
won={live.get('trades_won')} lost={live.get('trades_lost')} open={live.get('open_positions')}

Recalled database library:
{memory_block}

Recent dialog:
{hist_block}

User:
{message}
"""
        try:
            reply = self.ollama.generate(user_prompt, model=model, system=instructions)
        except OllamaError as exc:
            reply = (
                "Ollama is not reachable from this Windows brain. "
                f"{exc} Start Ollama, then retry. Live price is {live.get('price')}."
            )
        stored = self.brain.add_chat("assistant", reply)
        return {
            "ok": True,
            "message": stored,
            "model": model,
            "history": self.brain.chat_history(80),
        }

    def analyze_memory(self, memory_id: str) -> dict[str, Any]:
        memory = self.brain.get_memory(memory_id)
        live = runtime.snapshot()
        prompt = self.brain.get_setting("chat_prompt") or DEFAULT_CHAT_PROMPT
        instructions = self.brain.get_setting("chat_instructions") or DEFAULT_CHAT_INSTRUCTIONS
        model = self.brain.get_setting("text_model")
        body = f"""{prompt}

{instructions}

Analyze and memorize this library document for trading use.
Title: {memory['title']}
Kind: {memory['kind']}
Content:
{memory['content'][:12000]}

Live EURUSD/MT5 context: price={live.get('price')} session={(live.get('session') or {}).get('label')} P&L={live.get('profit')}
Summarize the lesson and how the EA should use it on FVG / Inverse FVG decisions.
"""
        try:
            reply = self.ollama.generate(body, model=model, system=instructions)
        except OllamaError as exc:
            reply = f"Analyze queued locally but Ollama is offline: {exc}"
        analysis = (
            f"ANALYZED MEMORY: {memory['title']}\n\n{reply}"
        )
        self.brain.add_chat("assistant", analysis)
        updated = self.brain.remember(
            kind=memory["kind"],
            title=memory["title"],
            content=memory["content"],
            source=memory.get("source") or "",
            tags=list(memory.get("tags") or []) + ["analyzed"],
            embedding=self.ollama.embed(f"{memory['title']}\n{reply[:2000]}"),
            metadata={**(memory.get("metadata") or {}), "last_analysis": reply[:4000]},
            memory_id=memory["id"],
        )
        return {"ok": True, "memory": updated, "analysis": reply, "ping": "RECEIVED"}
