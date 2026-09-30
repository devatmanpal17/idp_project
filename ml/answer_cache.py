"""Answer cache with exact top-k mutation validity for video scopes."""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone

from sqlalchemy import text


def cosine(a, b):
    numerator = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return numerator / norm if norm else -1.0


class AnswerCache:
    def __init__(self, rag):
        self.rag = rag
        self.engine = rag.vectors.engine
        self.lock = rag._lock
        self.hits = 0
        self.misses = 0
        self.prompt_version = os.getenv('B_PROMPT_VERSION', 'video-answer-v1')
        with self.engine.begin() as db:
            db.execute(text("""CREATE TABLE IF NOT EXISTS answer_cache (
                key TEXT PRIMARY KEY, scope TEXT NOT NULL, epoch INTEGER NOT NULL,
                query_vector_json TEXT NOT NULL, k INTEGER NOT NULL, kth_score REAL NOT NULL,
                retrieved_ids_json TEXT NOT NULL, response_json TEXT NOT NULL,
                created_at TEXT NOT NULL)"""))
            db.execute(text("""CREATE TABLE IF NOT EXISTS answer_cache_epochs (
                scope TEXT PRIMARY KEY, epoch INTEGER NOT NULL)"""))

    def key(self, question, scope, llm_model, k, topic):
        normal = ' '.join(question.casefold().split())
        value = [normal, scope, topic or '', llm_model, self.prompt_version, self.rag.model_version, k]
        return hashlib.sha256(json.dumps(value).encode()).hexdigest()

    def _epoch(self, db, scope):
        value = db.execute(text('SELECT epoch FROM answer_cache_epochs WHERE scope=:scope'),
                           {'scope': scope}).scalar()
        return int(value or 0)

    def get(self, key, scope):
        with self.lock, self.engine.connect() as db:
            row = db.execute(text('SELECT epoch,response_json,query_vector_json,k,retrieved_ids_json FROM answer_cache WHERE key=:key AND scope=:scope'),
                             {'key': key, 'scope': scope}).first()
            if row and row[0] == self._epoch(db, scope):
                vector = json.loads(row[2])
                if scope.startswith('scoped:'):
                    learner, video = scope.removeprefix('scoped:').split('|', 1)
                    from .scoped_store import unblob
                    active = [dict(item) for item in db.execute(text("""SELECT * FROM scoped_chunks
                        WHERE learner_key=:learner AND video_key=:video AND state='ACTIVE'"""),
                        {'learner': learner, 'video': video}).mappings()]
                    by_id = {item['chunk_id']: item for item in active}
                    ranked = sorted(((cosine(vector, unblob(item['vector'])), item)
                                     for item in active),
                                    key=lambda item: (-item[0], item[1]['chunk_id']))
                    exact_ids, seen = [], set()
                    for _, item in ranked:
                        if item['granularity'] == 'micro' and item['parent_id'] in by_id:
                            item = by_id[item['parent_id']]
                        if item['chroma_id'] in seen:
                            continue
                        exact_ids.append(item['chroma_id'])
                        seen.add(item['chroma_id'])
                        if len(exact_ids) >= row[3]:
                            break
                else:
                    active = db.execute(text("""SELECT id,vector_json FROM temporal_chunks
                        WHERE document_id=:scope AND state='ACTIVE'"""), {'scope': scope}).all()
                    exact_ids = [chunk_id for _, chunk_id in sorted(
                        ((cosine(vector, json.loads(raw)), chunk_id) for chunk_id, raw in active if raw),
                        key=lambda item: (-item[0], item[1]))[:row[3]]]
                if exact_ids == json.loads(row[4]):
                    self.hits += 1
                    return json.loads(row[1])
            self.misses += 1
            return None

    def put(self, key, scope, query_vector, k, chunks, response):
        # When fewer than k chunks exist, any insertion changes the result.
        kth = min((cosine(query_vector, self._vector(item['chunk_id'])) for item in chunks),
                  default=-2.0) if len(chunks) >= k else -2.0
        values = dict(key=key, scope=scope, vector=json.dumps(query_vector), k=k,
                      kth=kth, ids=json.dumps([item['chunk_id'] for item in chunks]),
                      response=json.dumps(response), created=datetime.now(timezone.utc).isoformat())
        with self.lock, self.engine.begin() as db:
            values['epoch'] = self._epoch(db, scope)
            db.execute(text("""INSERT INTO answer_cache
                (key,scope,epoch,query_vector_json,k,kth_score,retrieved_ids_json,response_json,created_at)
                VALUES (:key,:scope,:epoch,:vector,:k,:kth,:ids,:response,:created)
                ON CONFLICT(key) DO UPDATE SET epoch=excluded.epoch,
                query_vector_json=excluded.query_vector_json,k=excluded.k,
                kth_score=excluded.kth_score,retrieved_ids_json=excluded.retrieved_ids_json,
                response_json=excluded.response_json,created_at=excluded.created_at"""), values)

    def _vector(self, chunk_id):
        with self.engine.connect() as db:
            value = db.execute(text('SELECT vector_json FROM temporal_chunks WHERE id=:id'),
                               {'id': chunk_id}).scalar()
            if value:
                return json.loads(value)
            value = db.execute(text('SELECT vector FROM scoped_chunks WHERE chroma_id=:id'),
                               {'id': chunk_id}).scalar()
        if value:
            from .scoped_store import unblob
            return unblob(value)
        return []

    def insert(self, scope, vectors):
        if not vectors:
            return 0
        with self.lock, self.engine.begin() as db:
            rows = db.execute(text('SELECT key,query_vector_json,kth_score FROM answer_cache WHERE scope=:scope'),
                              {'scope': scope}).all()
            invalid = [key for key, query, score in rows if any(
                cosine(json.loads(query), vector) >= score for vector in vectors)]
            for key in invalid:
                db.execute(text('DELETE FROM answer_cache WHERE key=:key'), {'key': key})
            return len(invalid)

    def remove(self, scope, ids):
        removed = set(ids)
        if not removed:
            return 0
        with self.lock, self.engine.begin() as db:
            rows = db.execute(text('SELECT key,retrieved_ids_json FROM answer_cache WHERE scope=:scope'),
                              {'scope': scope}).all()
            invalid = [key for key, encoded in rows if removed.intersection(json.loads(encoded))]
            for key in invalid:
                db.execute(text('DELETE FROM answer_cache WHERE key=:key'), {'key': key})
            return len(invalid)

    def bump_epoch(self, scope):
        with self.lock, self.engine.begin() as db:
            db.execute(text("""INSERT INTO answer_cache_epochs VALUES (:scope,1)
                ON CONFLICT(scope) DO UPDATE SET epoch=epoch+1"""), {'scope': scope})

    def status(self):
        with self.engine.connect() as db:
            size = db.execute(text('SELECT COUNT(*) FROM answer_cache')).scalar()
        return {'entries': size, 'hits': self.hits, 'misses': self.misses,
                'hit_rate': self.hits / (self.hits + self.misses) if self.hits + self.misses else 0.0}
