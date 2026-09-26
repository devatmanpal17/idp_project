"""Persistent ChromaDB retrieval backed by Ollama embeddings."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional

import chromadb
from .metrics import metrics


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
        metrics.add("embedding_calls_total")
        started = time.perf_counter()
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
        metrics.add("embedding_ms_total", (time.perf_counter() - started) * 1000)
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

    def __init__(self, persist_directory: Optional[Path] = None, state_engine=None, embeddings=None) -> None:
        root = Path(__file__).resolve().parent.parent
        self.persist_directory = persist_directory or Path(
            os.getenv("CHROMA_PERSIST_DIR", str(root / "data" / "chroma"))
        )
        self._lock = RLock()
        from .vector_cache import VectorCache
        self.hot_cache = VectorCache(max_bytes=int(os.getenv('RAG_CACHE_BYTES', str(8 * 1024 * 1024))))
        self.embeddings = embeddings or OllamaEmbeddings()
        self.model_version = os.getenv("OLLAMA_EMBED_VERSION", self.embeddings.model)
        if embeddings is None:
            try:
                with urllib.request.urlopen(f"{self.embeddings.base_url}/api/tags", timeout=2) as response:
                    models = json.loads(response.read()).get('models', [])
                match = next((m for m in models if m.get('name', '').split(':')[0] == self.embeddings.model.split(':')[0]), None)
                if match and match.get('digest'):
                    self.model_version = f"{self.embeddings.model}:{match['digest']}"
            except (urllib.error.URLError, OSError, ValueError):
                # Explicitly version unavailable service configurations. Never mix with a digest collection.
                self.model_version += ':unresolved'
        suffix = hashlib.sha256(self.model_version.encode()).hexdigest()[:16]
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
            name=f"chaigaram_active_{suffix}",
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,
        )
        from .analytics import quiz_analytics
        from .vector_state import VectorState
        from .persistent_jobs import JobStore
        engine = state_engine if state_engine is not None else quiz_analytics.engine
        self.jobs = JobStore(engine)
        self.vectors = VectorState(engine, self)
        self.vectors.recover()

    def invalidate_cache(self) -> None:
        if hasattr(self, 'hot_cache'):
            self.hot_cache.clear()

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
        if (extra_metadata or {}).get('source_type') == 'video':
            raise ValueError('Video ingestion requires timestamped captions and observation intervals.')
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
                "model_version": self.model_version,
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
            self.invalidate_cache()
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
        return self.vectors.delete(unique_ids)

    def retrieve(
        self, query: str, topic: Optional[str] = None, top_k: int = 6,
        document_id: Optional[str] = None, require_topic: bool = False,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            key = json.dumps([self.model_version, query, topic, top_k, document_id, require_topic])
            cached = self.hot_cache.get(key)
            if cached is not None:
                return cached
            started = time.perf_counter()
            result = self._retrieve(query, topic, top_k, document_id, require_topic)
            self.hot_cache.put(key, result)
            metrics.add('retrieval_ms', (time.perf_counter() - started) * 1000)
            return result

    def _retrieve(
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

    def migrate_legacy(self, collection_name: str, dry_run: bool = True) -> dict:
        """Copy verifiably compatible document vectors; never infer or alter the source."""
        if collection_name == self.collection.name:
            raise ValueError('Migration source must differ from the active collection.')
        names = {getattr(item, 'name', item) for item in self.client.list_collections()}
        if collection_name not in names:
            raise ValueError('Legacy collection was not found.')
        source = self.client.get_collection(collection_name, embedding_function=None)
        copied, skipped = 0, 0
        with self._lock:
            for offset in range(0, source.count(), 250):
                batch = source.get(limit=250, offset=offset, include=['documents', 'metadatas', 'embeddings'])
                for index, chunk_id in enumerate(batch['ids']):
                    meta = (batch['metadatas'] or [])[index] or {}
                    # Old untyped transcript records might be videos: fail closed.
                    compatible = (meta.get('source_type') == 'document'
                                  and meta.get('model_version') == self.model_version
                                  and bool(meta.get('document_id')))
                    if not compatible or self.collection.get(ids=[chunk_id], include=[])['ids']:
                        skipped += 1
                        continue
                    if not dry_run:
                        self.collection.upsert(ids=[chunk_id], documents=[batch['documents'][index]],
                            embeddings=[batch['embeddings'][index]], metadatas=[meta])
                        self.invalidate_cache()
                    copied += 1
        return {'dry_run': dry_run, 'eligible' if dry_run else 'copied': copied,
                'skipped': skipped, 'source_collection': collection_name, 'embedding_calls': 0}

    def status(self) -> Dict[str, Any]:
        return {
            "vector_database": "chromadb",
            "collection": self.collection.name,
            "persist_directory": str(self.persist_directory),
            "storage_backend": self.storage_backend,
            "indexed_chunks": self.count,
            "topics_indexed": self.topics(),
            "embedding_service": self.embeddings.health(),
            "cache": self.hot_cache.status(),
        }


rag_engine = RAGEngine()
