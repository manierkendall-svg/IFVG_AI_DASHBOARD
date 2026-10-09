from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import httpx

from app.config import CONFIG


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self) -> None:
        self.host = CONFIG.ollama.host.rstrip("/")
        self.timeout = CONFIG.ollama.timeout_seconds

    def health(self) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=5.0) as client:
                tags = client.get(f"{self.host}/api/tags")
                tags.raise_for_status()
                payload = tags.json()
            models = [item.get("name") for item in payload.get("models", [])]
            return {"ok": True, "host": self.host, "models": models}
        except Exception as exc:
            return {"ok": False, "host": self.host, "error": str(exc), "models": []}

    def embed(self, text: str, model: str | None = None) -> list[float] | None:
        model = model or CONFIG.ollama.embed_model
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.host}/api/embeddings",
                    json={"model": model, "prompt": text[:8000]},
                )
                response.raise_for_status()
                data = response.json()
            embedding = data.get("embedding")
            if embedding:
                return embedding
        except Exception:
            pass
        return local_embed(text)

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        images: list[str] | None = None,
        system: str | None = None,
        json_mode: bool = False,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model or CONFIG.ollama.text_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.15},
        }
        if system:
            payload["system"] = system
        if images:
            payload["images"] = images
            payload["model"] = model or CONFIG.ollama.vision_model
        if json_mode:
            payload["format"] = "json"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.host}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
            return (data.get("response") or "").strip()
        except Exception as exc:
            raise OllamaError(str(exc)) from exc

    def describe_chart(self, image_b64: str, context: str) -> str:
        prompt = (
            "You are a price-action vision analyst. Describe the candlestick chart. "
            "Call out trend, liquidity sweeps, Fair Value Gaps, Inverse FVGs, "
            "displacement, and whether price is reacting to or filling imbalance. "
            "Be concrete. Context:\n"
            f"{context}"
        )
        return self.generate(prompt, images=[image_b64], model=CONFIG.ollama.vision_model)

    def decide(self, prompt: str, image_b64: str | None = None, system: str | None = None, model: str | None = None) -> dict[str, Any]:
        system = system or (
            "You are a disciplined ICT / SMC trade filter. "
            "You ACCEPT a trade only when FVG or Inverse FVG structure, "
            "displacement, and direction agree. Otherwise DENY. "
            "Return JSON only."
        )
        raw = self.generate(
            prompt,
            system=system,
            images=[image_b64] if image_b64 else None,
            model=model or (CONFIG.ollama.vision_model if image_b64 else CONFIG.ollama.text_model),
            json_mode=True,
        )
        parsed = _parse_json(raw)
        action = str(parsed.get("action", "DENY")).upper()
        if action not in {"ACCEPT", "DENY"}:
            action = "DENY"
        try:
            confidence = float(parsed.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(confidence, 1.0))
        return {
            "action": action,
            "confidence": confidence,
            "reason": str(parsed.get("reason") or raw)[:2000],
            "invalidation": parsed.get("invalidation", ""),
            "targets": parsed.get("targets", []),
            "raw": raw,
        }


def local_embed(text: str, dims: int = 96) -> list[float]:
    tokens = [token for token in text.lower().split() if token]
    vec = [0.0] * dims
    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8", errors="ignore")).hexdigest()
        idx = int(digest, 16) % dims
        vec[idx] += 1.0
    norm = math.sqrt(sum(item * item for item in vec))
    if norm:
        vec = [item / norm for item in vec]
    return vec


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}
