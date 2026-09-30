"""Durable sealed vectors and recoverable SQL -> ACTIVE Chroma promotion.

The local service serializes mutation and retrieval with the RAG lock. SQL stores
the authoritative promotion intent; Chroma upsert is idempotent on chunk identity.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from datetime import datetime, timezone

from sqlalchemy import text

from .metrics import metrics
from .temporal import Caption, Interval, covered, fingerprint, merge_intervals, temporal_chunks, watermark

log = logging.getLogger(__name__)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class VectorState:
    def __init__(self, engine, rag):
        self.engine, self.rag = engine, rag
        self.lock = rag._lock
        self.fault_hook = lambda stage: None
        with engine.begin() as db:
            for ddl in [
                """CREATE TABLE IF NOT EXISTS media_documents (
                id TEXT PRIMARY KEY, source TEXT NOT NULL, topic TEXT NOT NULL,
                revision TEXT NOT NULL, model_version TEXT NOT NULL, state TEXT NOT NULL,
                created_at TEXT NOT NULL, metrics_json TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS temporal_chunks (
                id TEXT PRIMARY KEY, document_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                text TEXT NOT NULL, start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL,
                state TEXT NOT NULL, model_version TEXT NOT NULL, vector_json TEXT,
                embedded_at TEXT, observation_verified_at TEXT, activated_at TEXT,
                promotion_sequence INTEGER NOT NULL DEFAULT 0)""",
                "CREATE INDEX IF NOT EXISTS temporal_document ON temporal_chunks(document_id, state)",
                """CREATE TABLE IF NOT EXISTS observation_sessions (
                id TEXT PRIMARY KEY, document_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                intervals_json TEXT NOT NULL, evidence TEXT NOT NULL, updated_at TEXT NOT NULL)""",
            ]:
                db.execute(text(ddl))

    def document(self, document_id: str) -> dict:
        with self.engine.connect() as db:
            row = db.execute(text("SELECT * FROM media_documents WHERE id=:id AND state='CURRENT'"),
                             {"id": document_id}).mappings().first()
        if not row or row['model_version'] != self.rag.model_version:
            raise ValueError("Unknown, stale or deleted media document; capture again.")
        return dict(row)

    def register(self, source: str, topic: str, captions: list[Caption]) -> dict:
        chunks, stats = temporal_chunks(captions)
        if not chunks:
            raise ValueError("No timestamped captions were supplied.")
        revision = fingerprint(source, chunks)
        document_id = hashlib.sha256(f'{source}|{revision}|{self.rag.model_version}'.encode()).hexdigest()[:32]
        with self.lock:
            with self.engine.connect() as db:
                old = db.execute(text("SELECT id FROM media_documents WHERE source=:source AND state='CURRENT' AND id<>:id"),
                                 {"source": source, "id": document_id}).scalars().all()
            # A changed snapshot invalidates old vectors AND old observation proof.
            if old:
                self.delete(list(old))
            with self.engine.begin() as db:
                existing = db.execute(text("SELECT state FROM media_documents WHERE id=:id"), {"id": document_id}).scalar()
                if existing == 'CURRENT':
                    return self.status(document_id)
                if existing:
                    raise ValueError("Deleted transcript identity cannot be reused; reload with a new source session.")
                db.execute(text("""INSERT INTO media_documents VALUES
                    (:id,:source,:topic,:revision,:model,'CURRENT',:created,:metrics)"""),
                    dict(id=document_id, source=source, topic=topic, revision=revision,
                         model=self.rag.model_version, created=now(), metrics=json.dumps(stats)))
                for index, chunk in enumerate(chunks):
                    db.execute(text("""INSERT INTO temporal_chunks
                        (id,document_id,ordinal,text,start_ms,end_ms,state,model_version)
                        VALUES (:id,:document,:ordinal,:text,:start,:end,'UNEMBEDDED',:model)"""),
                        dict(id=f'{document_id}_{index:06d}', document=document_id, ordinal=index,
                             text=chunk['text'], start=chunk['start_ms'], end=chunk['end_ms'], model=self.rag.model_version))
        return self.status(document_id)

    def intervals(self, document_id: str) -> list[list[int]]:
        with self.engine.connect() as db:
            rows = db.execute(text("SELECT intervals_json FROM observation_sessions WHERE document_id=:id"),
                              {"id": document_id}).scalars().all()
        return merge_intervals(Interval(start_ms=a, end_ms=b) for row in rows for a, b in json.loads(row))

    def observe(self, document_id: str, session_id: str, sequence: int,
                intervals: list[Interval], evidence: str) -> dict:
        with self.lock:
            self.document(document_id)
            with self.engine.begin() as db:
                old = db.execute(text("SELECT * FROM observation_sessions WHERE id=:id"),
                                 {"id": session_id}).mappings().first()
                if old and old['document_id'] != document_id:
                    raise ValueError("Observation session belongs to a different document.")
                if old and sequence <= old['sequence']:
                    return self.status(document_id)
                previous = [Interval(start_ms=a, end_ms=b) for a, b in json.loads(old['intervals_json'])] if old else []
                values = dict(id=session_id, document=document_id, sequence=sequence,
                              intervals=json.dumps(merge_intervals(previous + intervals)), evidence=evidence, updated=now())
                if old:
                    db.execute(text("""UPDATE observation_sessions SET sequence=:sequence,
                        intervals_json=:intervals,evidence=:evidence,updated_at=:updated WHERE id=:id"""), values)
                else:
                    db.execute(text("INSERT INTO observation_sessions VALUES (:id,:document,:sequence,:intervals,:evidence,:updated)"), values)
            self.promote(document_id)
            log.info('observation_interval_updated document=%s sequence=%s', document_id, sequence)
        return self.status(document_id)

    def pending(self, document_id: str) -> list[dict]:
        self.document(document_id)
        with self.engine.connect() as db:
            return [dict(r) for r in db.execute(text("""SELECT * FROM temporal_chunks
                WHERE document_id=:id AND state='UNEMBEDDED' ORDER BY ordinal"""), {'id': document_id}).mappings()]

    def embed_chunk(self, document_id: str, chunk_id: str) -> bool:
        # Serialize check + inference + persistence: duplicate jobs cannot infer twice.
        # Scheduler limits each non-preemptible unit to one cue.
        with self.lock:
            self.document(document_id)
            with self.engine.connect() as db:
                row = db.execute(text("SELECT * FROM temporal_chunks WHERE id=:id AND document_id=:doc"),
                                 {'id': chunk_id, 'doc': document_id}).mappings().first()
            if not row or row['state'] != 'UNEMBEDDED':
                return False
            started = time.perf_counter()
            vector = self.rag.embeddings.embed([row['text']])[0]
            if not vector or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vector):
                raise ValueError('Invalid embedding vector')
            with self.engine.begin() as db:
                db.execute(text("""UPDATE temporal_chunks SET state='SEALED',vector_json=:vector,
                    embedded_at=:now WHERE id=:id AND state='UNEMBEDDED'"""),
                    {'vector': json.dumps(vector), 'now': now(), 'id': chunk_id})
            metrics.add('speculative_embeddings_total')
            metrics.add('embedding_input_bytes', len(row['text'].encode()))
            metrics.add('speculative_embedding_ms', (time.perf_counter() - started) * 1000)
            log.info('vector_sealed chunk=%s', chunk_id)
            self.promote(document_id)
            return True

    def promote(self, document_id: str) -> int:
        with self.lock:
            document = self.document(document_id)
            observed = self.intervals(document_id)
            with self.engine.connect() as db:
                rows = db.execute(text("""SELECT * FROM temporal_chunks WHERE document_id=:id
                    AND state IN ('SEALED','PROMOTION_PENDING') ORDER BY ordinal"""), {'id': document_id}).mappings().all()
            promoted = 0
            for row in rows:
                if not covered(row['start_ms'], row['end_ms'], observed):
                    continue
                if row['model_version'] != self.rag.model_version:
                    raise ValueError('Embedding model changed; re-ingest transcript')
                started = time.perf_counter()
                with self.engine.begin() as db:
                    db.execute(text("""UPDATE temporal_chunks SET state='PROMOTION_PENDING',
                        observation_verified_at=:now,promotion_sequence=promotion_sequence+1
                        WHERE id=:id AND state='SEALED'"""), {'now': now(), 'id': row['id']})
                self.fault_hook('before_upsert')
                self.rag.collection.upsert(ids=[row['id']], embeddings=[json.loads(row['vector_json'])],
                    documents=[row['text']], metadatas=[{
                        'document_id': document_id, 'topic': document['topic'], 'course': document['topic'],
                        'source': document['source'], 'page_url': document['source'], 'source_type': 'video',
                        'media_start_ms': row['start_ms'], 'media_end_ms': row['end_ms'],
                        'model_version': row['model_version'], 'ingested_at': document['created_at'],
                        'timestamp': str(row['start_ms'] / 1000), 'observation_verified': True,
                    }])
                self.fault_hook('after_upsert')
                with self.engine.begin() as db:
                    db.execute(text("UPDATE temporal_chunks SET state='ACTIVE',activated_at=:now WHERE id=:id"),
                               {'id': row['id'], 'now': now()})
                if hasattr(self.rag, 'answer_cache'):
                    self.rag.answer_cache.insert(document_id, [json.loads(row['vector_json'])])
                self.rag.invalidate_cache()
                metrics.add('promoted_vectors_total')
                metrics.add('promotion_ms', (time.perf_counter() - started) * 1000)
                log.info('vector_promoted chunk=%s', row['id'])
                promoted += 1
            return promoted

    def delete(self, document_ids: list[str]) -> int:
        removed = 0
        with self.lock:
            for document_id in document_ids:
                self.rag.jobs.cancel_documents([document_id])
                with self.engine.begin() as db:
                    db.execute(text("UPDATE media_documents SET state='DELETING' WHERE id=:id"), {'id': document_id})
                entries = self.rag.collection.get(where={'document_id': document_id}, include=[])
                if hasattr(self.rag, 'answer_cache'):
                    self.rag.answer_cache.bump_epoch(document_id)
                if entries['ids']:
                    self.rag.collection.delete(ids=entries['ids'])
                    removed += len(entries['ids'])
                with self.engine.begin() as db:
                    db.execute(text('DELETE FROM temporal_chunks WHERE document_id=:id'), {'id': document_id})
                    db.execute(text('DELETE FROM observation_sessions WHERE document_id=:id'), {'id': document_id})
                    db.execute(text("UPDATE media_documents SET state='DELETED' WHERE id=:id"), {'id': document_id})
                self.rag.invalidate_cache()
        return removed

    def recover(self):
        with self.engine.connect() as db:
            rows = [dict(r) for r in db.execute(text('SELECT * FROM media_documents')).mappings()]
        for row in rows:
            if row['state'] == 'DELETING' or (row['state'] == 'CURRENT' and row['model_version'] != self.rag.model_version):
                self.delete([row['id']])
            elif row['state'] == 'CURRENT':
                self.promote(row['id'])

    def status(self, document_id: str) -> dict:
        self.document(document_id)
        intervals = self.intervals(document_id)
        with self.engine.connect() as db:
            counts = dict(db.execute(text('SELECT state,COUNT(*) FROM temporal_chunks WHERE document_id=:id GROUP BY state'),
                                     {'id': document_id}).all())
        return {'document_id': document_id, 'observed_intervals': intervals,
                'contiguous_watermark_ms': watermark(intervals), 'counts': counts}

    def diagnostics(self) -> list[dict]:
        with self.engine.connect() as db:
            ids = db.execute(text("SELECT id FROM media_documents WHERE state='CURRENT' AND model_version=:model"),
                             {'model': self.rag.model_version}).scalars().all()
        return [self.status(doc) for doc in ids]
