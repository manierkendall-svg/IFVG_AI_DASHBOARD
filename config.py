from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parent.parent


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class OllamaConfig(BaseModel):
    host: str = "http://127.0.0.1:11434"
    vision_model: str = "llava"
    text_model: str = "llama3.1"
    embed_model: str = "nomic-embed-text"
    timeout_seconds: int = 180


class BrainConfig(BaseModel):
    dir: str = "data/brain"
    knowledge_dir: str = "data/knowledge"
    upload_dir: str = "data/uploads"
    chart_dir: str = "data/charts"
    max_recall: int = 12
    min_similarity: float = 0.12


class TradingConfig(BaseModel):
    default_symbol: str = "EURUSD"
    default_timeframe: str = "M15"
    min_accept_confidence: float = 0.62
    fvg_min_gap_atr: float = 0.15
    ifvg_fill_ratio: float = 0.5
    lookback_bars: int = 120


class SecurityConfig(BaseModel):
    mt5_shared_key: str = "change-me-on-windows"


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    brain: BrainConfig = Field(default_factory=BrainConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)


def _load_yaml() -> dict[str, Any]:
    path = ROOT / "config.yaml"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_config() -> AppConfig:
    raw = _load_yaml()
    cfg = AppConfig.model_validate(raw)
    cfg.server.host = os.getenv("HOST", cfg.server.host)
    cfg.server.port = int(os.getenv("PORT", cfg.server.port))
    cfg.ollama.host = os.getenv("OLLAMA_HOST", cfg.ollama.host)
    cfg.ollama.vision_model = os.getenv("OLLAMA_VISION_MODEL", cfg.ollama.vision_model)
    cfg.ollama.text_model = os.getenv("OLLAMA_TEXT_MODEL", cfg.ollama.text_model)
    cfg.ollama.embed_model = os.getenv("OLLAMA_EMBED_MODEL", cfg.ollama.embed_model)
    cfg.brain.dir = os.getenv("BRAIN_DIR", cfg.brain.dir)
    cfg.brain.knowledge_dir = os.getenv("KNOWLEDGE_DIR", cfg.brain.knowledge_dir)
    cfg.brain.upload_dir = os.getenv("UPLOAD_DIR", cfg.brain.upload_dir)
    cfg.brain.chart_dir = os.getenv("CHART_DIR", cfg.brain.chart_dir)
    cfg.security.mt5_shared_key = os.getenv("MT5_SHARED_KEY", cfg.security.mt5_shared_key)
    cfg.trading.default_symbol = os.getenv("DEFAULT_SYMBOL", cfg.trading.default_symbol)
    cfg.trading.default_timeframe = os.getenv("DEFAULT_TIMEFRAME", cfg.trading.default_timeframe)
    cfg.trading.min_accept_confidence = float(
        os.getenv("MIN_ACCEPT_CONFIDENCE", cfg.trading.min_accept_confidence)
    )
    return cfg


CONFIG = load_config()


def resolve_path(relative: str) -> Path:
    path = Path(relative)
    if not path.is_absolute():
        path = ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path
