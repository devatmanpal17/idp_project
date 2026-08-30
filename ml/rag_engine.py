"""Persistent ChromaDB retrieval backed by Ollama embeddings."""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional

import chromadb


class RAGConfigurationError(RuntimeError):
    """Raised when the local embedding service is unavailable."""


class OllamaEmbeddings:
    """Small Ollama /api/embed client used for both indexing and querying."""

    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.model = os.getenv("OLLAMA_EMBED_MODEL", "embeddinggemma")

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        request = urllib.request.Request(
            f"{self.base_url}/api/embed",
            data=json.dumps({"model": self.model, "input": texts}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RAGConfigurationError(
                "Ollama embeddings are unavailable. Start Ollama and run "
                f"`ollama pull {self.model}`."
            ) from exc
        embeddings = body.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise RAGConfigurationError("Ollama returned an invalid embeddings response.")
        return embeddings

    def health(self) -> Dict[str, Any]:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            names = [model.get("name", "") for model in payload.get("models", [])]
            return {
                "online": True,
                "embedding_model": self.model,
                "embedding_model_ready": any(
                    name == self.model or name.startswith(f"{self.model}:") for name in names
                ),
                "models": names,
            }
        except Exception:
            return {
                "online": False,
                "embedding_model": self.model,
                "embedding_model_ready": False,
                "models": [],
            }


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _chunk_text(text: str, chunk_words: int = 220, overlap_words: int = 40) -> List[str]:
    """Split text on paragraph/sentence boundaries with a small word overlap."""
    clean = text.replace("\r\n", "\n").strip()
    if not clean:
        return []
    units = [
        _normalise(part)
        for part in re.split(r"\n{2,}|(?<=[.!?])\s+(?=[A-Z0-9])", clean)
        if _normalise(part)
    ]
    chunks: List[str] = []
    current: List[str] = []
    for unit in units:
        words = unit.split()
        if current and len(current) + len(words) > chunk_words:
            chunks.append(" ".join(current))
            current = current[-overlap_words:] if overlap_words else []
        while len(words) > chunk_words:
            room = max(1, chunk_words - len(current))
            current.extend(words[:room])
            words = words[room:]
            chunks.append(" ".join(current))
            current = current[-overlap_words:] if overlap_words else []
        current.extend(words)
    if current:
        chunks.append(" ".join(current))
    return [chunk for chunk in chunks if len(chunk.split()) >= 3]


class RAGEngine:
    """Persistent semantic index. Similarities are raw cosine scores from Chroma."""

    def __init__(self, persist_directory: Optional[Path] = None) -> None:
        root = Path(__file__).resolve().parent.parent
        self.persist_directory = persist_directory or Path(
            os.getenv("CHROMA_PERSIST_DIR", str(root / "data" / "chroma"))
        )
        self._lock = RLock()
        self.embeddings = OllamaEmbeddings()
        chroma_host = os.getenv("CHROMA_HOST", "").strip()
        if chroma_host:
            self.client = chromadb.HttpClient(
                host=chroma_host,
                port=int(os.getenv("CHROMA_PORT", "8000")),
                ssl=os.getenv("CHROMA_SSL", "false").lower() == "true",
            )
            self.storage_backend = f"remote:{chroma_host}"
        else:
            self.persist_directory.mkdir(parents=True, exist_ok=True)
            self.client = chromadb.PersistentClient(path=str(self.persist_directory))
            self.storage_backend = "local"
        self.collection = self.client.get_or_create_collection(
            name=os.getenv("CHROMA_COLLECTION", "chaigaram_lessons"),
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,
        )

    @property
    def count(self) -> int:
        return self.collection.count()

    @property
    def all_chunks(self) -> List[Dict[str, Any]]:
        result = self.collection.get(include=["documents", "metadatas"])
        return [
            {"id": chunk_id, "text": document or "", **(metadata or {})}
            for chunk_id, document, metadata in zip(
                result.get("ids", []),
                result.get("documents") or [],
                result.get("metadatas") or [],
            )
        ]

    def topics(self) -> List[str]:
        result = self.collection.get(include=["metadatas"])
        return sorted(
            {
                str(metadata.get("topic"))
                for metadata in (result.get("metadatas") or [])
                if metadata and metadata.get("topic")
            }
        )

    def ingest_document(
        self,
        text: str,
        topic: str,
        source: str,
        course: str = "",
        timestamp: str = "",
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalised = text.strip()
        chunks = _chunk_text(normalised)
        if not chunks:
            raise ValueError("Document contains no indexable text.")
        document_id = hashlib.sha256(
            f"{source}|{topic}|{normalised}".encode("utf-8")
        ).hexdigest()[:16]
        ids = [f"{document_id}_{index:04d}" for index in range(len(chunks))]
        safe_extra = {
            key: value
            for key, value in (extra_metadata or {}).items()
            if isinstance(value, (str, int, float, bool)) and value is not None
        }
        metadatas = [
            {
                "document_id": document_id,
                "chunk_index": index,
                "topic": topic or "Uncategorised",
                "course": course or "",
                "source": source or "User document",
                "timestamp": timestamp or "",
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                **safe_extra,
            }
            for index in range(len(chunks))
        ]
        vectors = self.embeddings.embed(chunks)
        with self._lock:
            self.collection.upsert(
                ids=ids,
                documents=chunks,
                metadatas=metadatas,
                embeddings=vectors,
            )
        return {
            "document_id": document_id,
            "indexed": True,
            "chunks_indexed": len(chunks),
            "total_chunks": self.count,
        }

    def ingest_transcript(
        self,
        text: str,
        topic: str,
        course: str,
        timestamp: str,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.ingest_document(
            text=text,
            topic=topic or "Current lesson",
            source=f"Transcript: {course or 'Browser capture'}",
            course=course,
            timestamp=timestamp,
            extra_metadata=extra_metadata,
        )

    def catalogue_records(self) -> List[Dict[str, Any]]:
        """Return persisted chunk metadata used to derive the live dashboard catalogue."""
        result = self.collection.get(include=["documents", "metadatas"])
        return [
            {
                "chunk_id": chunk_id,
                "text": document or "",
                **(metadata or {}),
            }
            for chunk_id, document, metadata in zip(
                result.get("ids", []),
                result.get("documents") or [],
                result.get("metadatas") or [],
            )
        ]

    def delete_documents(self, document_ids: List[str]) -> int:
        """Remove complete source documents so they cannot be used by retrieval again."""
        unique_ids = sorted({str(value).strip() for value in document_ids if str(value).strip()})
        if not unique_ids:
            return 0
        with self._lock:
            result = self.collection.get(
                where={"document_id": {"$in": unique_ids}},
                include=[],
            )
            chunk_ids = list(result.get("ids") or [])
            if chunk_ids:
                self.collection.delete(ids=chunk_ids)
        return len(chunk_ids)

    def retrieve(
        self, query: str, topic: Optional[str] = None, top_k: int = 6,
        document_id: Optional[str] = None, require_topic: bool = False,
    ) -> List[Dict[str, Any]]:
        if self.count == 0:
            return []
        if require_topic and topic and not self._topic_exists(topic):
            return []
        query_text = _normalise(f"{topic or ''} {query}")
        if not query_text:
            raise ValueError("A query or topic is required.")
        query_vector = self.embeddings.embed([query_text])[0]
        requested = min(max(top_k, 1), self.count)
        kwargs: Dict[str, Any] = {
            "query_embeddings": [query_vector],
            "n_results": requested,
            "include": ["documents", "metadatas", "distances"],
        }
        if document_id:
            document_records = self.collection.get(where={"document_id": document_id}, include=[])
            if not document_records.get("ids"):
                return []
            kwargs["where"] = {"document_id": document_id}
            kwargs["n_results"] = min(requested, len(document_records.get("ids", [])))
        elif topic:
            if not self._topic_exists(topic):
                return []
            topic_records = self.collection.get(where={"topic": topic}, include=[])
            kwargs["where"] = {"topic": topic}
            kwargs["n_results"] = min(requested, len(topic_records.get("ids", [])))
        result = self.collection.query(**kwargs)
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        chunks: List[Dict[str, Any]] = []
        for chunk_id, document, metadata, distance in zip(ids, docs, metas, distances):
            meta = metadata or {}
            similarity = max(-1.0, min(1.0, 1.0 - float(distance)))
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "topic": meta.get("topic", "Uncategorised"),
                    "course": meta.get("course", ""),
                    "source": meta.get("source", ""),
                    "timestamp": meta.get("timestamp", ""),
                    "snippet": document or "",
                    "similarity": round(similarity, 4),
                    "distance": round(float(distance), 4),
                    "token_count": len((document or "").split()),
                }
            )
        return chunks

    def _topic_exists(self, topic: str) -> bool:
        result = self.collection.get(where={"topic": topic}, limit=1, include=[])
        return bool(result.get("ids"))

    def status(self) -> Dict[str, Any]:
        return {
            "vector_database": "chromadb",
            "collection": self.collection.name,
            "persist_directory": str(self.persist_directory),
            "storage_backend": self.storage_backend,
            "indexed_chunks": self.count,
            "topics_indexed": self.topics(),
            "embedding_service": self.embeddings.health(),
        }


rag_engine = RAGEngine()
