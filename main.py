from __future__ import annotations

import socket
import threading
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, File, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.analyzer import TradeAnalyzer
from app.brain import BrainStore
from app.chat import ChatRoom
from app.config import CONFIG, ROOT, resolve_path
from app.demo_market import sample_bullish_setup
from app.ingest import Ingestor
from app.ollama_client import OllamaClient
from app.prompts import (
    DEFAULT_CHAT_INSTRUCTIONS,
    DEFAULT_CHAT_PROMPT,
    DEFAULT_EA_INSTRUCTIONS,
    DEFAULT_EA_PROMPT,
)
from app.runtime import runtime
from app.seed import seed_core_knowledge


class Candle(BaseModel):
    time: Any | None = None
    timestamp: Any | None = None
    open: float
    high: float
    low: float
    close: float
    volume: float | None = 0


class AnalyzeRequest(BaseModel):
    symbol: str | None = None
    timeframe: str | None = None
    direction: str | None = None
    side: str | None = None
    entry: float | None = None
    price: float | None = None
    sl: float | None = None
    tp: float | None = None
    ticket: int | None = None
    comment: str | None = None
    setup: str | None = None
    candles: list[Candle] = Field(default_factory=list)
    screenshot: str | None = None
    image_path: str | None = None
    image_base64: str | None = None


class MemoryNote(BaseModel):
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)


class SettingsPatch(BaseModel):
    paused: bool | None = None
    min_accept_confidence: float | None = None
    vision_model: str | None = None
    text_model: str | None = None
    embed_model: str | None = None
    default_symbol: str | None = None
    default_timeframe: str | None = None
    mode: str | None = None
    default_lots: float | None = None
    default_direction: str | None = None
    ea_prompt: str | None = None
    ea_instructions: str | None = None
    chat_prompt: str | None = None
    chat_instructions: str | None = None


class ChatMessage(BaseModel):
    message: str


class PromptUpload(BaseModel):
    target: str
    content: str = ""


class TradeCommand(BaseModel):
    action: str
    direction: str | None = None
    lots: float | None = None
    symbol: str | None = None
    sl: float | None = None
    tp: float | None = None
    comment: str | None = None


class CommandAck(BaseModel):
    id: str
    status: str = "done"
    result: dict[str, Any] = Field(default_factory=dict)
    action: str | None = None


ALLOWED_COMMANDS = {
    "ping",
    "open_trade",
    "close_trade",
    "close_all",
    "pause",
    "resume",
}


class Hub:
    def __init__(self) -> None:
        self.clients: list[WebSocket] = []
        self.lock = threading.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        with self.lock:
            self.clients.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        with self.lock:
            if ws in self.clients:
                self.clients.remove(ws)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        with self.lock:
            clients = list(self.clients)
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


hub = Hub()
brain = BrainStore()
ollama = OllamaClient()
ingestor = Ingestor(brain, ollama)
analyzer = TradeAnalyzer(brain, ollama)
chatroom = ChatRoom(brain, ollama)
started_at = time.time()


def _auth(x_mt5_key: str | None) -> None:
    expected = brain.get_setting("mt5_shared_key") or CONFIG.security.mt5_shared_key
    if expected and expected != "change-me-on-windows":
        if not x_mt5_key or x_mt5_key != expected:
            raise HTTPException(status_code=401, detail="Invalid MT5 shared key")


def _local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"


@asynccontextmanager
async def lifespan(_: FastAPI):
    resolve_path(CONFIG.brain.dir)
    resolve_path(CONFIG.brain.knowledge_dir)
    resolve_path(CONFIG.brain.upload_dir)
    resolve_path(CONFIG.brain.chart_dir)
    seed_core_knowledge(ingestor)
    brain.log_event("system", "Vision RAG brain started")
    yield
    brain.log_event("system", "Vision RAG brain stopped")
    brain.close()


app = FastAPI(title="IFVG_AI_EA: METATRADER 5", lifespan=lifespan)
static_dir = ROOT / "web"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    index = ROOT / "web" / "index.html"
    return HTMLResponse(index.read_text(encoding="utf-8"))


@app.get("/manifest.json")
def manifest() -> FileResponse:
    return FileResponse(ROOT / "web" / "manifest.json")


@app.get("/sw.js")
def service_worker() -> FileResponse:
    return FileResponse(ROOT / "web" / "sw.js", media_type="text/javascript")


@app.get("/api/health")
def health() -> dict[str, Any]:
    ollama_health = ollama.health()
    live = runtime.snapshot()
    return {
        "ok": True,
        "uptime_sec": int(time.time() - started_at),
        "paused": brain.get_setting("paused") == "true",
        "ollama": ollama_health,
        "stats": brain.stats(),
        "lan_url": f"http://{_local_ip()}:{CONFIG.server.port}",
        "live": live,
        "last_heartbeat": live.get("raw") or {},
        "ea_connected": live.get("connected"),
    }


@app.get("/api/state")
def state() -> dict[str, Any]:
    return {
        "settings": brain.settings(),
        "stats": brain.stats(),
        "memories": brain.list_memories(limit=80),
        "decisions": brain.recent_decisions(30),
        "events": brain.recent_events(40),
        "commands": brain.recent_commands(12),
        "chat": brain.chat_history(80),
        "live": runtime.snapshot(),
        "health": health(),
        "models": {
            "text": brain.get_setting("text_model"),
            "vision": brain.get_setting("vision_model"),
        },
        "prompts": {
            "ea_prompt": brain.get_setting("ea_prompt") or DEFAULT_EA_PROMPT,
            "ea_instructions": brain.get_setting("ea_instructions") or DEFAULT_EA_INSTRUCTIONS,
            "chat_prompt": brain.get_setting("chat_prompt") or DEFAULT_CHAT_PROMPT,
            "chat_instructions": brain.get_setting("chat_instructions") or DEFAULT_CHAT_INSTRUCTIONS,
        },
    }


@app.post("/api/settings")
def patch_settings(body: SettingsPatch) -> dict[str, Any]:
    data = body.model_dump(exclude_none=True)
    for key, value in data.items():
        if isinstance(value, bool):
            brain.set_setting(key, "true" if value else "false")
        else:
            brain.set_setting(key, str(value))
    brain.log_event("control", "Settings updated from dashboard", data)
    return {"ok": True, "settings": brain.settings()}


@app.post("/api/control/{action}")
async def control(action: str) -> dict[str, Any]:
    action = action.lower()
    if action == "pause":
        brain.set_setting("paused", "true")
        command = brain.enqueue_command("pause")
        await hub.broadcast({"type": "command", "data": command})
    elif action == "resume":
        brain.set_setting("paused", "false")
        command = brain.enqueue_command("resume")
        await hub.broadcast({"type": "command", "data": command})
    elif action == "rescan":
        ingested = ingestor.scan_knowledge_folder()
        return {"ok": True, "ingested": len(ingested)}
    else:
        raise HTTPException(status_code=400, detail="Unknown action")
    brain.log_event("control", f"Brain {action}")
    return {"ok": True, "paused": brain.get_setting("paused") == "true"}


@app.get("/api/memories")
def list_memories(kind: str | None = None) -> dict[str, Any]:
    return {"memories": brain.list_memories(kind=kind)}


@app.post("/api/memories")
def add_memory(note: MemoryNote) -> dict[str, Any]:
    memory = ingestor.ingest_text(note.title, note.content, tags=note.tags or ["note"])
    return {"ok": True, "memory": memory}


@app.post("/api/memories/upload")
async def upload_memory(
    file: UploadFile = File(...),
    tags: str = "",
) -> dict[str, Any]:
    data = await file.read()
    tag_list = [item.strip() for item in tags.split(",") if item.strip()]
    memory = ingestor.ingest_bytes(file.filename or "upload.bin", data, tags=tag_list)
    return {"ok": True, "memory": memory}


@app.post("/api/memories/scan")
def scan_memories() -> dict[str, Any]:
    ingested = ingestor.scan_knowledge_folder()
    return {"ok": True, "count": len(ingested)}


@app.post("/api/memories/{memory_id}/forget")
def forget_memory(memory_id: str) -> dict[str, Any]:
    try:
        brain.forget(memory_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "ping": "DELETED"}


@app.post("/api/memories/{memory_id}/analyze")
def analyze_memory(memory_id: str) -> dict[str, Any]:
    try:
        return chatroom.analyze_memory(memory_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Memory not found") from exc


@app.get("/api/chat")
def get_chat() -> dict[str, Any]:
    return {
        "ok": True,
        "history": brain.chat_history(80),
        "model": brain.get_setting("text_model"),
    }


@app.post("/api/chat")
def post_chat(body: ChatMessage) -> dict[str, Any]:
    try:
        return chatroom.ask(body.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


PROMPT_TARGETS = {
    "ea_prompt",
    "ea_instructions",
    "chat_prompt",
    "chat_instructions",
}


@app.post("/api/prompts")
def save_prompts(body: SettingsPatch) -> dict[str, Any]:
    data = body.model_dump(exclude_none=True)
    saved = {}
    for key, value in data.items():
        if key in PROMPT_TARGETS:
            brain.set_setting(key, str(value))
            saved[key] = True
    brain.log_event("prompts", "Prompts updated", saved)
    return {"ok": True, "ping": "RECEIVED", "saved": saved, "settings": brain.settings()}


@app.post("/api/prompts/upload")
async def upload_prompt(target: str, file: UploadFile = File(...)) -> dict[str, Any]:
    if target not in PROMPT_TARGETS:
        raise HTTPException(status_code=400, detail="Unknown prompt target")
    data = await file.read()
    text = data.decode("utf-8", errors="ignore")
    brain.set_setting(target, text)
    brain.log_event("prompts", f"Uploaded {target}", {"bytes": len(data)})
    return {"ok": True, "ping": "RECEIVED", "target": target, "chars": len(text)}


@app.post("/api/demo/analyze")
async def demo_analyze() -> dict[str, Any]:
    payload = sample_bullish_setup()
    result = analyzer.analyze(payload)
    await hub.broadcast({"type": "decision", "data": result})
    return result


@app.post("/api/analyze")
async def analyze(body: AnalyzeRequest) -> dict[str, Any]:
    payload = body.model_dump()
    payload["candles"] = [c.model_dump() for c in body.candles]
    result = analyzer.analyze(payload)
    await hub.broadcast({"type": "decision", "data": result})
    return result


@app.post("/mt5/analyze")
async def mt5_analyze(
    body: AnalyzeRequest,
    x_mt5_key: str | None = Header(default=None),
) -> JSONResponse:
    _auth(x_mt5_key)
    payload = body.model_dump()
    payload["candles"] = [c.model_dump() for c in body.candles]
    result = analyzer.analyze(payload)
    await hub.broadcast({"type": "decision", "data": result})
    compact = {
        "ok": True,
        "action": result["action"],
        "confidence": result["confidence"],
        "reason": result["reason"],
        "ticket": result.get("ticket"),
        "symbol": result.get("symbol"),
        "timeframe": result.get("timeframe"),
        "source": result.get("source"),
    }
    return JSONResponse(compact)


@app.post("/mt5/heartbeat")
async def mt5_heartbeat(
    payload: dict[str, Any],
    x_mt5_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _auth(x_mt5_key)
    snapshot = runtime.update_heartbeat(payload)
    commands = brain.next_commands()
    await hub.broadcast({"type": "live", "data": runtime.snapshot()})
    return {
        "ok": True,
        "paused": brain.get_setting("paused") == "true",
        "min_accept_confidence": float(
            brain.get_setting("min_accept_confidence", str(CONFIG.trading.min_accept_confidence))
        ),
        "commands": commands,
        "session": snapshot.get("session"),
    }


@app.get("/mt5/commands")
def mt5_commands(x_mt5_key: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(x_mt5_key)
    return {"ok": True, "commands": brain.next_commands()}


@app.post("/mt5/commands/ack")
async def mt5_ack_command(
    body: CommandAck,
    x_mt5_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _auth(x_mt5_key)
    updated = brain.ack_command(body.id, status=body.status, result=body.result)
    if not updated:
        raise HTTPException(status_code=404, detail="Unknown command")
    runtime.set_command_result({"id": body.id, "action": body.action or updated["action"], **body.result})
    await hub.broadcast({"type": "command_result", "data": updated})
    return {"ok": True, "command": updated}


@app.post("/api/commands")
async def queue_command(body: TradeCommand) -> dict[str, Any]:
    action = body.action.lower().strip()
    if action not in ALLOWED_COMMANDS:
        raise HTTPException(status_code=400, detail="Unknown command")
    if action == "pause":
        brain.set_setting("paused", "true")
    if action == "resume":
        brain.set_setting("paused", "false")
    payload = body.model_dump(exclude_none=True)
    if action == "open_trade":
        payload["direction"] = (body.direction or brain.get_setting("default_direction") or "buy").lower()
        payload["lots"] = body.lots or float(brain.get_setting("default_lots") or 0.10)
        payload["symbol"] = body.symbol or brain.get_setting("default_symbol")
    command = brain.enqueue_command(action, payload)
    await hub.broadcast({"type": "command", "data": command})
    return {"ok": True, "command": command, "ea_connected": runtime.connected()}


@app.post("/webhook/mt5")
async def webhook_mt5(
    payload: dict[str, Any],
    x_mt5_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _auth(x_mt5_key)
    snapshot = runtime.update_heartbeat(payload)
    await hub.broadcast({"type": "live", "data": runtime.snapshot()})
    return {"ok": True, "live": snapshot, "commands": brain.next_commands()}


@app.get("/api/live")
def live_state() -> dict[str, Any]:
    return {"ok": True, "live": runtime.snapshot(), "commands": brain.recent_commands(8)}


@app.get("/api/decisions")
def decisions() -> dict[str, Any]:
    return {"decisions": brain.recent_decisions(50)}


@app.websocket("/ws")
async def ws_feed(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        await ws.send_json({"type": "hello", "data": brain.stats()})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)


@app.get("/api/qr")
def qr_payload() -> dict[str, Any]:
    url = f"http://{_local_ip()}:{CONFIG.server.port}"
    return {"url": url, "ip": _local_ip(), "port": CONFIG.server.port}


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=CONFIG.server.host,
        port=CONFIG.server.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
