from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from app.brain import BrainStore, extract_text_from_file, file_digest
from app.config import CONFIG, resolve_path
from app.ollama_client import OllamaClient


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


class Ingestor:
    def __init__(self, brain: BrainStore, ollama: OllamaClient) -> None:
        self.brain = brain
        self.ollama = ollama
        self.knowledge_dir = resolve_path(CONFIG.brain.knowledge_dir)
        self.upload_dir = resolve_path(CONFIG.brain.upload_dir)

    def ingest_path(self, path: Path, tags: list[str] | None = None) -> dict[str, Any]:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(str(path))
        digest = file_digest(path)
        text = extract_text_from_file(path)
        kind = "image" if path.suffix.lower() in IMAGE_EXTENSIONS else "document"
        title = path.stem.replace("_", " ").replace("-", " ")
        embedding = self.ollama.embed(f"{title}\n{text[:4000]}")
        memory = self.brain.remember(
            kind=kind,
            title=title,
            content=text[:20000] or f"Binary/image memory from {path.name}",
            source=str(path),
            tags=tags or [kind, path.suffix.lower().lstrip(".")],
            embedding=embedding,
            metadata={"sha256": digest, "filename": path.name, "bytes": path.stat().st_size},
            memory_id=digest,
        )
        return memory

    def ingest_bytes(
        self,
        filename: str,
        data: bytes,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        dest = self.upload_dir / Path(filename).name
        dest.write_bytes(data)
        knowledge_copy = self.knowledge_dir / dest.name
        shutil.copy2(dest, knowledge_copy)
        return self.ingest_path(knowledge_copy, tags=tags)

    def ingest_text(self, title: str, content: str, tags: list[str] | None = None) -> dict[str, Any]:
        dest = self.knowledge_dir / f"{title.replace(' ', '_').lower()}.md"
        dest.write_text(content, encoding="utf-8")
        embedding = self.ollama.embed(f"{title}\n{content[:4000]}")
        return self.brain.remember(
            kind="note",
            title=title,
            content=content,
            source=str(dest),
            tags=tags or ["note"],
            embedding=embedding,
        )

    def scan_knowledge_folder(self) -> list[dict[str, Any]]:
        ingested: list[dict[str, Any]] = []
        for path in sorted(self.knowledge_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() not in {".sqlite", ".db"}:
                ingested.append(self.ingest_path(path))
        return ingested
