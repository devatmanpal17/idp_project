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
from .residency import canonical_model, residency


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
            data=json.dumps({"model": self.model, "input": texts,
                             "keep_alive": residency.keep_alive(self.model)}).encode("utf-8"),
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
                    canonical_model(name) == canonical_model(self.model) for name in names
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

    def __init__(self, persist_directory: Optional[Path] = None, state_engine=None,
                 embeddings=None, analytics_store=None) -> None:
        root = Path(__file__).resolve().parent.parent
        self.persist_directory = persist_directory or Path(
            os.getenv("CHROMA_PERSIST_DIR", str(root / "data" / "chroma"))
        )
        self._lock = RLock()
        from .vector_cache import VectorCache
        self.hot_cache = VectorCache(max_bytes=int(os.getenv('RAG_CACHE_BYTES', str(8 * 1024 * 1024))))
        self.query_vector_cache = VectorCache(
            max_bytes=int(os.getenv('RAG_QUERY_VECTOR_CACHE_BYTES', str(1024 * 1024))))
        self.embeddings = embeddings or OllamaEmbeddings()
        self.model_version = os.getenv("OLLAMA_EMBED_VERSION", self.embeddings.model)
        if embeddings is None:
            try:
                with urllib.request.urlopen(f"{self.embeddings.base_url}/api/tags", timeout=2) as response:
                    models = json.loads(response.read()).get('models', [])
                requested = canonical_model(self.embeddings.model)
                match = next((m for m in models
                              if canonical_model(m.get('name', m.get('model', ''))) == requested), None)
                if match and match.get('digest'):
                    self.model_version = f"{self.embeddings.model}:{match['digest']}"
                else:
                    self.model_version += ':unresolved'
            except (urllib.error.URLError, OSError, ValueError):
                # Explicitly version unavailable service configurations. Never mix with a digest collection.
                self.model_version += ':unresolved'
            if (self.model_version.endswith(':unresolved')
                    and os.getenv('CHAI_REQUIRE_RESOLVED_EMBEDDING_MODEL', '').lower() == 'true'):
                # Hosted recovery must never invalidate saved vectors because of a
                # transient inventory outage between provisioning and API startup.
                raise RAGConfigurationError('Embedding model identity is unavailable; retry startup after model setup.')
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
        self.analytics_store = analytics_store if analytics_store is not None else quiz_analytics
        self._cache_recall_model = None
        from .vector_state import VectorState
        from .persistent_jobs import JobStore
        engine = state_engine if state_engine is not None else quiz_analytics.engine
        self.jobs = JobStore(engine)
        self.vectors = VectorState(engine, self)
        self.vectors.recover()
        from .scoped_store import ScopedStore
        self.scoped = ScopedStore(self)
        self.scoped.recover()
        from .transfer import TransferEngine
        self.scoped.transfer = TransferEngine(self.scoped)
        from .evidence_lease import EvidenceLease
        self.leases = EvidenceLease(self)
        self.leases.recover()
        from .answer_cache import AnswerCache
        self.answer_cache = AnswerCache(self)
        self.scoped.transfer.recover()

    def invalidate_cache(self) -> None:
        if hasattr(self, 'hot_cache'):
            self.hot_cache.clear()
            self.query_vector_cache.clear()
            self._cache_recall_model = None

    def _cache_priority(self, topic: Optional[str]) -> float:
        """Use assessed recall as cache utility; unassessed topics stay neutral."""
        if not topic:
            return 0.5
        if self._cache_recall_model is None:
            from .recall import RecallModel
            self._cache_recall_model = RecallModel(self.analytics_store.attempts())
        forecast = self._cache_recall_model.forecast(topic)
        probability = forecast['probability']
        return 0.5 if probability is None else 1.0 - probability

    @property
    def count(self) -> int:
        return self.collection.count()

    @property
    def all_chunks(self) -> List[Dict[str, Any]]:
        result = self.collection.get(where={"scope_kind": {"$ne": "scoped"}},
                                     include=["documents", "metadatas"])
        return [
            {"id": chunk_id, "text": document or "", **(metadata or {})}
            for chunk_id, document, metadata in zip(
                result.get("ids", []),
                result.get("documents") or [],
                result.get("metadatas") or [],
            )
        ]

    def topics(self) -> List[str]:
        result = self.collection.get(where={"scope_kind": {"$ne": "scoped"}},
                                     include=["metadatas"])
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
        from sqlalchemy import text as sql_text
        with self.vectors.engine.connect() as db:
            blocked_hashes = set(db.execute(sql_text("""SELECT content_hash FROM scoped_chunks
                WHERE state='DEMOTED'""")).scalars())
            blocked_hashes.update(hashlib.sha256(_normalise(value).encode()).hexdigest()
                for value in db.execute(sql_text("SELECT text FROM temporal_chunks WHERE state='DEMOTED'")).scalars())
        if any(hashlib.sha256(_normalise(chunk).encode()).hexdigest() in blocked_hashes
               for chunk in chunks):
            raise ValueError('This evidence is locked until the quiz is submitted.')
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
        result = self.collection.get(where={"scope_kind": {"$ne": "scoped"}},
                                     include=["documents", "metadatas"])
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
        learner_key: Optional[str] = None, video_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if learner_key and video_key:
            return self.scoped.retrieve(learner_key, video_key, query, top_k, topic)
        with self._lock:
            key = json.dumps([self.model_version, query, topic, top_k, document_id, require_topic])
            cached = self.hot_cache.get(key)
            if cached is not None:
                from .evidence_snapshot import active_chunks
                return active_chunks(self, cached)
            started = time.perf_counter()
            result = self._retrieve(query, topic, top_k, document_id, require_topic)
            from .evidence_snapshot import active_chunks
            result = active_chunks(self, result)
            result_topics = {item['topic'] for item in result}
            cache_topic = topic or (next(iter(result_topics)) if len(result_topics) == 1 else None)
            self.hot_cache.put(key, result, priority=self._cache_priority(cache_topic))
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
        requested = min(max(top_k, 1), self.count)
        kwargs: Dict[str, Any] = {
            "n_results": requested,
            "include": ["documents", "metadatas", "distances"],
            "where": {"scope_kind": {"$ne": "scoped"}},
        }
        cache_topic = topic
        if document_id:
            document_records = self.collection.get(where={"document_id": document_id}, include=['metadatas'])
            if not document_records.get("ids"):
                return []
            document_topics = {str(meta.get('topic')) for meta in (document_records.get('metadatas') or [])
                               if meta and meta.get('topic')}
            if not cache_topic and len(document_topics) == 1:
                cache_topic = next(iter(document_topics))
            kwargs["where"] = {"$and": [
                {"document_id": document_id}, {"scope_kind": {"$ne": "scoped"}}]}
            kwargs["n_results"] = min(requested, len(document_records.get("ids", [])))
        elif topic:
            if not self._topic_exists(topic):
                return []
            topic_records = self.collection.get(where={"topic": topic}, include=[])
            kwargs["where"] = {"$and": [
                {"topic": topic}, {"scope_kind": {"$ne": "scoped"}}]}
            kwargs["n_results"] = min(requested, len(topic_records.get("ids", [])))
        query_text = _normalise(f"{topic or ''} {query}")
        if not query_text:
            raise ValueError("A query or topic is required.")
        vector_key = json.dumps([self.model_version, query_text])
        query_vector = self.query_vector_cache.get(vector_key)
        if query_vector is None:
            query_vector = self.embeddings.embed([query_text])[0]
            self.query_vector_cache.put(vector_key, query_vector,
                                        priority=self._cache_priority(cache_topic))
        kwargs['query_embeddings'] = [query_vector]
        result = self.collection.query(**kwargs)
        if document_id and os.getenv('B_VERIFY_EXACT', 'true').lower() == 'true':
            from sqlalchemy import text as sql_text
            from .answer_cache import cosine
            with self.vectors.engine.connect() as db:
                media = db.execute(sql_text("SELECT topic,source FROM media_documents WHERE id=:id AND state='CURRENT'"),
                                   {'id': document_id}).mappings().first()
                if media:
                    rows = db.execute(sql_text("""SELECT * FROM temporal_chunks
                        WHERE document_id=:id AND state='ACTIVE'"""), {'id': document_id}).mappings().all()
            if media:
                ranked = sorted(((cosine(query_vector, json.loads(row['vector_json'])), row['id'], row)
                                 for row in rows if row['vector_json']), key=lambda item: (-item[0], item[1]))[:top_k]
                result = {
                    'ids': [[item[1] for item in ranked]],
                    'documents': [[item[2]['text'] for item in ranked]],
                    'metadatas': [[{'topic': media['topic'], 'course': media['topic'],
                                   'source': media['source'], 'timestamp': str(item[2]['start_ms'] / 1000)}
                                   for item in ranked]],
                    'distances': [[1.0 - item[0] for item in ranked]],
                }
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
            "query_vector_cache": self.query_vector_cache.status(),
        }


rag_engine = RAGEngine()
