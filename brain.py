from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from app.config import CONFIG, resolve_path
from app.prompts import (
    DEFAULT_CHAT_INSTRUCTIONS,
    DEFAULT_CHAT_PROMPT,
    DEFAULT_EA_INSTRUCTIONS,
    DEFAULT_EA_PROMPT,
)


TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".yml", ".yaml", ".log"}
DOC_EXTENSIONS = {".pdf", ".docx"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def _now() -> float:
    return time.time()


SYNONYMS = {
    "ifvg": ["ifvg", "inverse", "fvg", "imbalance"],
    "fvg": ["fvg", "gap", "imbalance", "inefficiency"],
    "bullish": ["bullish", "buy", "long"],
    "bearish": ["bearish", "sell", "short"],
}


def tokenize(text: str) -> list[str]:
    raw = [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 1]
    expanded: list[str] = []
    for token in raw:
        expanded.append(token)
        expanded.extend(SYNONYMS.get(token, []))
    return expanded


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def lexical_score(query: str, text: str) -> float:
    q = set(tokenize(query))
    t = set(tokenize(text))
    if not q or not t:
        return 0.0
    return len(q & t) / len(q | t)


class BrainStore:
    """Persistent memory vault. Files become reusable trading knowledge, not Q&A pairs."""

    def __init__(self) -> None:
        self.dir = resolve_path(CONFIG.brain.dir)
        self.db_path = self.dir / "brain.sqlite"
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT,
                    tags TEXT,
                    embedding TEXT,
                    metadata TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    use_count INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    symbol TEXT,
                    timeframe TEXT,
                    action TEXT,
                    confidence REAL,
                    reason TEXT,
                    payload TEXT,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload TEXT,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commands (
                    id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    payload TEXT,
                    status TEXT NOT NULL,
                    result TEXT,
                    created_at REAL NOT NULL,
                    ack_at REAL
                );
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )
            self._conn.commit()
            self._ensure_defaults()

    def _ensure_defaults(self) -> None:
        defaults = {
            "paused": "false",
            "min_accept_confidence": str(CONFIG.trading.min_accept_confidence),
            "vision_model": CONFIG.ollama.vision_model,
            "text_model": CONFIG.ollama.text_model,
            "embed_model": CONFIG.ollama.embed_model,
            "default_symbol": CONFIG.trading.default_symbol,
            "default_timeframe": CONFIG.trading.default_timeframe,
            "mode": "live",
            "default_lots": "0.10",
            "default_direction": "buy",
            "ea_prompt": DEFAULT_EA_PROMPT,
            "ea_instructions": DEFAULT_EA_INSTRUCTIONS,
            "chat_prompt": DEFAULT_CHAT_PROMPT,
            "chat_instructions": DEFAULT_CHAT_INSTRUCTIONS,
        }
        for key, value in defaults.items():
            self._conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
                (key, value),
            )
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def log_event(self, event_type: str, message: str, payload: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events(id, event_type, message, payload, created_at) VALUES(?,?,?,?,?)",
                (str(uuid.uuid4()), event_type, message, json.dumps(payload or {}), _now()),
            )
            self._conn.commit()

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self._conn.commit()

    def settings(self) -> dict[str, str]:
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def remember(
        self,
        kind: str,
        title: str,
        content: str,
        source: str = "",
        tags: list[str] | None = None,
        embedding: list[float] | None = None,
        metadata: dict[str, Any] | None = None,
        memory_id: str | None = None,
    ) -> dict[str, Any]:
        memory_id = memory_id or str(uuid.uuid4())
        now = _now()
        with self._lock:
            existing = self._conn.execute(
                "SELECT created_at FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
            created = existing["created_at"] if existing else now
            self._conn.execute(
                """
                INSERT INTO memories(id, kind, title, content, source, tags, embedding, metadata, created_at, updated_at, use_count)
                VALUES(?,?,?,?,?,?,?,?,?,?,0)
                ON CONFLICT(id) DO UPDATE SET
                    kind=excluded.kind,
                    title=excluded.title,
                    content=excluded.content,
                    source=excluded.source,
                    tags=excluded.tags,
                    embedding=excluded.embedding,
                    metadata=excluded.metadata,
                    updated_at=excluded.updated_at
                """,
                (
                    memory_id,
                    kind,
                    title,
                    content,
                    source,
                    json.dumps(tags or []),
                    json.dumps(embedding) if embedding else None,
                    json.dumps(metadata or {}),
                    created,
                    now,
                ),
            )
            self._conn.commit()
        memory = self.get_memory(memory_id)
        self.log_event("memory", f"Memorized {kind}: {title}", {"id": memory_id})
        return memory

    def get_memory(self, memory_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if not row:
            raise KeyError(memory_id)
        return self._row_to_memory(row)

    def list_memories(self, kind: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            if kind:
                rows = self._conn.execute(
                    "SELECT * FROM memories WHERE kind = ? ORDER BY updated_at DESC LIMIT ?",
                    (kind, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def forget(self, memory_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            self._conn.commit()
        self.log_event("memory", f"Deleted memory {memory_id}")

    def add_chat(self, role: str, content: str) -> dict[str, Any]:
        item = {
            "id": str(uuid.uuid4()),
            "role": role,
            "content": content,
            "created_at": _now(),
        }
        with self._lock:
            self._conn.execute(
                "INSERT INTO chats(id, role, content, created_at) VALUES(:id, :role, :content, :created_at)",
                item,
            )
            self._conn.commit()
        return item

    def chat_history(self, limit: int = 80) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM chats ORDER BY created_at ASC"
            ).fetchall()
        items = [dict(row) for row in rows]
        return items[-limit:]

    def recall(self, query: str, embeddings: list[float] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        limit = limit or CONFIG.brain.max_recall
        memories = self.list_memories(limit=500)
        scored: list[dict[str, Any]] = []
        for memory in memories:
            lex = lexical_score(query, f"{memory['title']} {memory['content']} {' '.join(memory['tags'])}")
            vec = 0.0
            if embeddings and memory.get("embedding"):
                vec = cosine(embeddings, memory["embedding"])
            score = max(lex, vec)
            if vec and lex:
                score = max(score, (0.55 * vec) + (0.45 * lex))
            if score >= CONFIG.brain.min_similarity:
                item = dict(memory)
                item["score"] = round(score, 4)
                scored.append(item)
        scored.sort(key=lambda item: item["score"], reverse=True)
        selected = scored[:limit]
        with self._lock:
            for item in selected:
                self._conn.execute(
                    "UPDATE memories SET use_count = use_count + 1 WHERE id = ?",
                    (item["id"],),
                )
            self._conn.commit()
        return selected

    def save_decision(self, payload: dict[str, Any]) -> dict[str, Any]:
        decision_id = str(uuid.uuid4())
        record = {
            "id": decision_id,
            "symbol": payload.get("symbol", ""),
            "timeframe": payload.get("timeframe", ""),
            "action": payload.get("action", "DENY"),
            "confidence": float(payload.get("confidence", 0)),
            "reason": payload.get("reason", ""),
            "payload": json.dumps(payload),
            "created_at": _now(),
        }
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO decisions(id, symbol, timeframe, action, confidence, reason, payload, created_at)
                VALUES(:id, :symbol, :timeframe, :action, :confidence, :reason, :payload, :created_at)
                """,
                record,
            )
            self._conn.commit()
        self.log_event("decision", f"{record['action']} {record['symbol']} {record['timeframe']}", payload)
        return record

    def recent_decisions(self, limit: int = 40) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM decisions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"] or "{}")
            out.append(item)
        return out

    def enqueue_command(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        command_id = str(uuid.uuid4())
        record = {
            "id": command_id,
            "action": action,
            "payload": json.dumps(payload or {}),
            "status": "queued",
            "result": None,
            "created_at": _now(),
            "ack_at": None,
        }
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO commands(id, action, payload, status, result, created_at, ack_at)
                VALUES(:id, :action, :payload, :status, :result, :created_at, :ack_at)
                """,
                record,
            )
            self._conn.commit()
        self.log_event("command", f"Queued {action}", {"id": command_id, **(payload or {})})
        item = dict(record)
        item["payload"] = payload or {}
        return item

    def next_commands(self, limit: int = 8) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM commands WHERE status = 'queued' ORDER BY created_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_command(row) for row in rows]

    def ack_command(self, command_id: str, status: str = "done", result: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
            if not row:
                return None
            self._conn.execute(
                "UPDATE commands SET status = ?, result = ?, ack_at = ? WHERE id = ?",
                (status, json.dumps(result or {}), _now(), command_id),
            )
            self._conn.commit()
            updated = self._conn.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
        return self._row_to_command(updated) if updated else None

    def recent_commands(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM commands ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_command(row) for row in rows]

    def _row_to_command(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["payload"] = json.loads(item["payload"] or "{}")
        item["result"] = json.loads(item["result"]) if item.get("result") else None
        return item

    def stats(self) -> dict[str, Any]:
        with self._lock:
            memory_count = self._conn.execute("SELECT COUNT(*) AS n FROM memories").fetchone()["n"]
            decision_count = self._conn.execute("SELECT COUNT(*) AS n FROM decisions").fetchone()["n"]
            accept_count = self._conn.execute(
                "SELECT COUNT(*) AS n FROM decisions WHERE action = 'ACCEPT'"
            ).fetchone()["n"]
            deny_count = self._conn.execute(
                "SELECT COUNT(*) AS n FROM decisions WHERE action = 'DENY'"
            ).fetchone()["n"]
        return {
            "memories": memory_count,
            "decisions": decision_count,
            "accepted": accept_count,
            "denied": deny_count,
            "paused": self.get_setting("paused") == "true",
        }

    def _row_to_memory(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["tags"] = json.loads(item["tags"] or "[]")
        item["metadata"] = json.loads(item["metadata"] or "{}")
        item["embedding"] = json.loads(item["embedding"]) if item["embedding"] else None
        return item


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def extract_text_from_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    if suffix == ".docx":
        from docx import Document

        document = Document(str(path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    if suffix in IMAGE_EXTENSIONS:
        return f"Chart or image memory stored from {path.name}."
    return path.read_text(encoding="utf-8", errors="ignore")
