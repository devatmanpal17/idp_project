"""Durable, reversible quiz evidence leases for timestamped video vectors."""
from __future__ import annotations

import json
import math
import os
import uuid
from datetime import datetime, timedelta, timezone
from threading import Event, Thread

from sqlalchemy import text


def _now():
    return datetime.now(timezone.utc)


def _cosine(a, b):
    numerator = sum(x * y for x, y in zip(a, b))
    denominator = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return numerator / denominator if denominator else -1.0


class EvidenceLease:
    def __init__(self, rag):
        self.rag = rag
        self.engine = rag.vectors.engine
        self.lock = rag._lock
        # A high default limits unrelated evidence; temporal overlap is checked separately.
        self.near_cos = float(os.getenv('A_NEAR_DUP_COS', '0.97'))
        self.seconds_per_question = int(os.getenv('A_SECONDS_PER_QUESTION', '180'))
        self.grace_seconds = int(os.getenv('A_GRACE_SECONDS', '120'))
        with self.engine.begin() as db:
            db.execute(text("""CREATE TABLE IF NOT EXISTS evidence_leases (
                id TEXT PRIMARY KEY, quiz_id TEXT UNIQUE NOT NULL,
                document_id TEXT NOT NULL, opened_at TEXT NOT NULL,
                expires_at TEXT NOT NULL, state TEXT NOT NULL)"""))
            db.execute(text("""CREATE TABLE IF NOT EXISTS evidence_lease_chunks (
                lease_id TEXT NOT NULL, chunk_id TEXT NOT NULL,
                PRIMARY KEY (lease_id, chunk_id))"""))
            db.execute(text("""CREATE TABLE IF NOT EXISTS evidence_lease_evidence (
                quiz_id TEXT PRIMARY KEY, questions_json TEXT NOT NULL)"""))

    def _rows(self, document_id):
        with self.engine.connect() as db:
            return [dict(row) for row in db.execute(text("""SELECT * FROM temporal_chunks
                WHERE document_id=:id AND state IN ('ACTIVE','DEMOTED')"""),
                {'id': document_id}).mappings()]

    def open(self, quiz_id, document_id, questions):
        with self.lock:
            self.expire()
            with self.engine.connect() as db:
                existing = db.execute(text('SELECT id FROM evidence_leases WHERE quiz_id=:quiz'),
                                      {'quiz': quiz_id}).scalar()
            if existing:
                return existing
            rows = self._rows(document_id)
            by_id = {row['id']: row for row in rows}
            evidence = {citation for question in questions for citation in question['citations']}
            evidence &= by_id.keys()
            if not evidence:
                raise ValueError('Quiz has no active video citations to lease.')
            selected = set(evidence)
            vectors = {row['id']: json.loads(row['vector_json']) for row in rows if row['vector_json']}
            for row in rows:
                if row['id'] in selected:
                    continue
                overlaps = any(row['start_ms'] < by_id[ref]['end_ms'] and
                               by_id[ref]['start_ms'] < row['end_ms'] for ref in evidence)
                nearby = row['id'] in vectors and any(
                    ref in vectors and _cosine(vectors[row['id']], vectors[ref]) >= self.near_cos
                    for ref in evidence)
                if overlaps or nearby:
                    selected.add(row['id'])
            lease_id = uuid.uuid4().hex
            opened = _now()
            expires = opened + timedelta(seconds=len(questions) * self.seconds_per_question + self.grace_seconds)
            with self.engine.begin() as db:
                db.execute(text("""INSERT INTO evidence_leases VALUES
                    (:id,:quiz,:doc,:opened,:expires,'OPEN')"""),
                    dict(id=lease_id, quiz=quiz_id, doc=document_id,
                         opened=opened.isoformat(), expires=expires.isoformat()))
                for chunk_id in selected:
                    db.execute(text('INSERT INTO evidence_lease_chunks VALUES (:lease,:chunk)'),
                               {'lease': lease_id, 'chunk': chunk_id})
                    db.execute(text("""UPDATE temporal_chunks SET state='DEMOTED'
                        WHERE id=:id AND state='ACTIVE'"""), {'id': chunk_id})
            self.rag.collection.delete(ids=sorted(selected))
            if hasattr(self.rag, 'answer_cache'):
                self.rag.answer_cache.remove(document_id, selected)
            self.rag.invalidate_cache()
            return lease_id

    def open_scoped(self, quiz_id, learner, video, questions):
        from .scoped_store import unblob
        scope = f'scoped:{learner}|{video}'
        with self.lock:
            self.expire()
            with self.engine.connect() as db:
                existing = db.execute(text('SELECT id,state FROM evidence_leases WHERE quiz_id=:quiz'),
                                      {'quiz': quiz_id}).first()
                if existing and existing.state != 'OPEN':
                    return existing.id
                rows = [dict(row) for row in db.execute(text("""SELECT * FROM scoped_chunks
                    WHERE learner_key=:learner AND video_key=:video
                    AND state IN ('ACTIVE','DEMOTED','SEALED')"""),
                    {'learner': learner, 'video': video}).mappings()]
            by_id = {row['chroma_id']: row for row in rows}
            evidence = {citation for question in questions for citation in question['citations']}
            evidence &= by_id.keys()
            if not evidence:
                raise ValueError('Quiz has no active scoped citations to lease.')
            selected = set(evidence)
            for row in rows:
                if any(row['chunk_id'] == by_id[ref]['parent_id'] or
                       row['parent_id'] == by_id[ref]['chunk_id'] or
                       (row['parent_id'] and row['parent_id'] == by_id[ref]['parent_id']) or
                       (row['t_start'] < by_id[ref]['t_end'] and
                        by_id[ref]['t_start'] < row['t_end']) or
                       _cosine(unblob(row['vector']), unblob(by_id[ref]['vector'])) >= self.near_cos
                       for ref in evidence):
                    selected.add(row['chroma_id'])
            # Follow transcript alignment into other versions watched by this learner.
            for other in self.rag.scoped.transfer._other_videos(learner, video):
                blocks = self.rag.scoped.transfer.align(learner, video, other)
                if not blocks:
                    continue
                with self.engine.connect() as db:
                    counterparts = [dict(row) for row in db.execute(text("""SELECT * FROM scoped_chunks
                        WHERE learner_key=:learner AND video_key=:video
                        AND state IN ('ACTIVE','DEMOTED','SEALED')"""),
                        {'learner': learner, 'video': other}).mappings()]
                for chroma_id in list(selected):
                    source_row = by_id.get(chroma_id)
                    if not source_row:
                        continue
                    for block in blocks:
                        if (source_row['t_start'] < block['source_start'] - 1 or
                            source_row['t_end'] > block['source_end'] + 1):
                            continue
                        scale = (block['target_end'] - block['target_start']) / (
                            block['source_end'] - block['source_start'])
                        mapped_start = block['target_start'] + (source_row['t_start'] - block['source_start']) * scale
                        mapped_end = block['target_start'] + (source_row['t_end'] - block['source_start']) * scale
                        for row in counterparts:
                            if row['t_start'] < mapped_end and mapped_start < row['t_end']:
                                selected.add(row['chroma_id'])
            lease_id = existing.id if existing else uuid.uuid4().hex
            opened = _now()
            expires = opened + timedelta(seconds=len(questions) * self.seconds_per_question + self.grace_seconds)
            with self.engine.begin() as db:
                db.execute(text("""INSERT OR IGNORE INTO evidence_leases VALUES
                    (:id,:quiz,:scope,:opened,:expires,'OPEN')"""),
                    {'id': lease_id, 'quiz': quiz_id, 'scope': scope,
                     'opened': opened.isoformat(), 'expires': expires.isoformat()})
                db.execute(text('INSERT OR IGNORE INTO evidence_lease_evidence VALUES (:quiz,:questions)'),
                           {'quiz': quiz_id, 'questions': json.dumps(questions)})
                for chroma_id in selected:
                    added = db.execute(text('INSERT OR IGNORE INTO evidence_lease_chunks VALUES (:lease,:chunk)'),
                                       {'lease': lease_id, 'chunk': chroma_id})
                    if not added.rowcount:
                        continue
                    db.execute(text("""UPDATE scoped_chunks SET
                        state=CASE WHEN state='ACTIVE' THEN 'DEMOTED' ELSE state END,
                        demote_refcount=demote_refcount+1 WHERE chroma_id=:id"""),
                        {'id': chroma_id})
            self.rag.collection.delete(ids=sorted(selected))
            if hasattr(self.rag, 'answer_cache'):
                with self.engine.connect() as db:
                    scopes = db.execute(text("""SELECT chroma_id,video_key FROM scoped_chunks
                        WHERE chroma_id IN (""" + ','.join(f':id{i}' for i in range(len(selected))) + ')'),
                        {f'id{i}': value for i, value in enumerate(selected)}).all()
                by_video = {}
                for chunk_id, item_video in scopes:
                    by_video.setdefault(item_video, []).append(chunk_id)
                for item_video, ids in by_video.items():
                    self.rag.answer_cache.remove(f'scoped:{learner}|{item_video}', ids)
            self.rag.invalidate_cache()
            return lease_id

    def refresh_scoped(self, learner):
        """Include newly sealed copies before either observation path can promote them."""
        with self.lock, self.engine.connect() as db:
            leases = db.execute(text('''SELECT l.quiz_id,l.document_id,e.questions_json
                FROM evidence_leases l JOIN evidence_lease_evidence e ON e.quiz_id=l.quiz_id
                WHERE l.state='OPEN' ''')).all()
        prefix = f'scoped:{learner}|'
        for quiz, scope, questions in leases:
            if scope.startswith(prefix):
                self.open_scoped(quiz, learner, scope[len(prefix):], json.loads(questions))

    def close(self, quiz_id):
        with self.lock:
            with self.engine.begin() as db:
                lease = db.execute(text("SELECT id FROM evidence_leases WHERE quiz_id=:quiz AND state='OPEN'"),
                                   {'quiz': quiz_id}).scalar()
                if not lease:
                    return 0
                ids = db.execute(text('SELECT chunk_id FROM evidence_lease_chunks WHERE lease_id=:id'),
                                 {'id': lease}).scalars().all()
                scope = db.execute(text('SELECT document_id FROM evidence_leases WHERE id=:id'),
                                   {'id': lease}).scalar_one()
                db.execute(text("UPDATE evidence_leases SET state='CLOSED' WHERE id=:id AND state='OPEN'"),
                           {'id': lease})
                restore = []
                for chunk_id in ids:
                    if scope.startswith('scoped:'):
                        db.execute(text("""UPDATE scoped_chunks SET
                            demote_refcount=CASE WHEN demote_refcount>0 THEN demote_refcount-1 ELSE 0 END
                            WHERE chroma_id=:id"""), {'id': chunk_id})
                    held = db.execute(text("""SELECT COUNT(*) FROM evidence_lease_chunks c
                        JOIN evidence_leases l ON l.id=c.lease_id
                        WHERE c.chunk_id=:id AND l.state='OPEN'"""), {'id': chunk_id}).scalar()
                    if not held:
                        if scope.startswith('scoped:'):
                            changed = db.execute(text("""UPDATE scoped_chunks SET state='ACTIVE',
                                demote_refcount=0 WHERE chroma_id=:id AND state='DEMOTED'"""),
                                {'id': chunk_id})
                        else:
                            changed = db.execute(text("""UPDATE temporal_chunks SET state='ACTIVE'
                                WHERE id=:id AND state='DEMOTED'"""), {'id': chunk_id})
                        if changed.rowcount:
                            restore.append(chunk_id)
            if scope.startswith('scoped:'):
                with self.engine.connect() as db:
                    rows = [dict(row) for chunk_id in restore for row in db.execute(
                        text('SELECT * FROM scoped_chunks WHERE chroma_id=:id'),
                        {'id': chunk_id}).mappings()]
                for row in rows:
                    self.rag.scoped._upsert(row)
            else:
                self._upsert(restore)
            if restore and hasattr(self.rag, 'answer_cache'):
                if scope.startswith('scoped:'):
                    from .scoped_store import unblob
                    by_video = {}
                    for row in rows:
                        by_video.setdefault(row['video_key'], []).append(unblob(row['vector']))
                    learner = scope.removeprefix('scoped:').split('|', 1)[0]
                    for video, vectors in by_video.items():
                        self.rag.answer_cache.insert(f'scoped:{learner}|{video}', vectors)
                else:
                    self.rag.answer_cache.insert(
                        self._document_for_chunk(restore[0]), [self._vector(chunk_id) for chunk_id in restore])
            self.rag.invalidate_cache()
            if scope.startswith('scoped:'):
                learner = scope.removeprefix('scoped:').split('|', 1)[0]
                with self.engine.connect() as db:
                    videos = db.execute(text('SELECT video_key FROM scoped_videos WHERE learner_key=:learner'),
                                        {'learner': learner}).scalars().all()
                for video in videos:
                    self.rag.scoped.promote(learner, video)
                    self.rag.scoped.transfer.on_observation(learner, video)
            return len(restore)

    def _document_for_chunk(self, chunk_id):
        with self.engine.connect() as db:
            return db.execute(text('SELECT document_id FROM temporal_chunks WHERE id=:id'),
                              {'id': chunk_id}).scalar_one()

    def _vector(self, chunk_id):
        with self.engine.connect() as db:
            raw = db.execute(text('SELECT vector_json FROM temporal_chunks WHERE id=:id'),
                             {'id': chunk_id}).scalar_one()
        return json.loads(raw)

    def _upsert(self, ids):
        if not ids:
            return
        with self.engine.connect() as db:
            rows = [dict(row) for row in db.execute(text("""SELECT c.*,d.topic,d.source,d.created_at
                FROM temporal_chunks c JOIN media_documents d ON d.id=c.document_id
                WHERE c.id IN (""" + ','.join(f':id{i}' for i in range(len(ids))) + ')'),
                {f'id{i}': value for i, value in enumerate(ids)}).mappings()]
        for row in rows:
            self.rag.collection.upsert(ids=[row['id']], documents=[row['text']],
                embeddings=[json.loads(row['vector_json'])], metadatas=[{
                    'document_id': row['document_id'], 'topic': row['topic'],
                    'course': row['topic'], 'source': row['source'],
                    'page_url': row['source'], 'source_type': 'video',
                    'media_start_ms': row['start_ms'], 'media_end_ms': row['end_ms'],
                    'model_version': row['model_version'], 'ingested_at': row['created_at'],
                    'timestamp': str(row['start_ms'] / 1000), 'observation_verified': True,
                }])

    def expire(self):
        with self.lock:
            with self.engine.connect() as db:
                quizzes = db.execute(text("""SELECT quiz_id FROM evidence_leases
                    WHERE state='OPEN' AND expires_at<=:now"""),
                    {'now': _now().isoformat()}).scalars().all()
            for quiz in quizzes:
                self.close(quiz)
            return len(quizzes)

    def recover(self):
        with self.lock:
            self.expire()
            with self.engine.connect() as db:
                rows = db.execute(text("""SELECT lc.chunk_id FROM evidence_lease_chunks lc
                    JOIN evidence_leases l ON l.id=lc.lease_id
                    WHERE l.state='OPEN'""")).scalars().all()
            if rows:
                with self.engine.begin() as db:
                    for chunk_id in rows:
                        db.execute(text("UPDATE temporal_chunks SET state='DEMOTED' WHERE id=:id"),
                                   {'id': chunk_id})
                        db.execute(text("""UPDATE scoped_chunks SET
                            state=CASE WHEN state='ACTIVE' THEN 'DEMOTED' ELSE state END,
                            demote_refcount=(SELECT COUNT(*) FROM evidence_lease_chunks lc
                              JOIN evidence_leases l ON l.id=lc.lease_id
                              WHERE lc.chunk_id=:id AND l.state='OPEN')
                            WHERE chroma_id=:id"""),
                                   {'id': chunk_id})
                self.rag.collection.delete(ids=sorted(set(rows)))
                self.rag.invalidate_cache()
            # SQL commits before Chroma mutations. Repair interrupted restores too.
            with self.engine.connect() as db:
                active = db.execute(text("SELECT id FROM temporal_chunks WHERE state='ACTIVE'" )).scalars().all()
            present = set(self.rag.collection.get(include=[])['ids'])
            self._upsert([chunk_id for chunk_id in active if chunk_id not in present])

    def would_hide(self, query, document_id, top_k, topic=None):
        """Return only a boolean; no leased text or ID enters the answer prompt."""
        with self.lock:
            with self.engine.connect() as db:
                has_lease = db.execute(text("""SELECT COUNT(*) FROM evidence_leases
                    WHERE document_id=:doc AND state='OPEN'"""), {'doc': document_id}).scalar()
            if not has_lease:
                return False
            rows = self._rows(document_id)
            if not rows:
                return False
            from .rag_engine import _normalise
            query_text = _normalise(f'{topic or ""} {query}')
            key = json.dumps([self.rag.model_version, query_text])
            vector = self.rag.query_vector_cache.get(key)
            if vector is None:
                vector = self.rag.embeddings.embed([query_text])[0]
                self.rag.query_vector_cache.put(key, vector)
            ranked = sorted(((_cosine(vector, json.loads(row['vector_json'])), row['id'], row['state'])
                             for row in rows if row['vector_json']), reverse=True)
            return any(state == 'DEMOTED' for _, _, state in ranked[:top_k])

    def would_hide_scoped(self, query, learner, video, top_k, topic=None):
        from .rag_engine import _normalise
        from .scoped_store import unblob
        scope = f'scoped:{learner}|{video}'
        if not self.has_open(scope):
            return False
        with self.engine.connect() as db:
            rows = db.execute(text("""SELECT state,vector,chroma_id FROM scoped_chunks
                WHERE learner_key=:learner AND video_key=:video
                AND state IN ('ACTIVE','DEMOTED')"""),
                {'learner': learner, 'video': video}).all()
        query_text = _normalise(f'{topic or ""} {query}')
        key = json.dumps([self.rag.model_version, query_text])
        vector = self.rag.query_vector_cache.get(key)
        if vector is None:
            vector = self.rag.embeddings.embed([query_text])[0]
            self.rag.query_vector_cache.put(key, vector)
        ranked = sorted(((_cosine(vector, unblob(raw)), chunk_id, state)
                         for state, raw, chunk_id in rows), reverse=True)
        return any(state == 'DEMOTED' for _, _, state in ranked[:top_k])

    def status(self):
        with self.engine.connect() as db:
            return db.execute(text("SELECT COUNT(*) FROM evidence_leases WHERE state='OPEN'")).scalar()

    def has_open(self, document_id):
        with self.engine.connect() as db:
            if document_id.startswith('scoped:'):
                learner, video = document_id.removeprefix('scoped:').split('|', 1)
                if db.execute(text('''SELECT 1 FROM scoped_chunks WHERE learner_key=:learner
                    AND video_key=:video AND demote_refcount>0 LIMIT 1'''),
                    {'learner': learner, 'video': video}).scalar():
                    return True
            return bool(db.execute(text("""SELECT COUNT(*) FROM evidence_leases
                WHERE state='OPEN' AND document_id=:doc"""), {'doc': document_id}).scalar())

    def start_sweeper(self):
        stop = Event()

        def run():
            while not stop.wait(5):
                try:
                    self.expire()
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception('Evidence lease sweep failed')

        Thread(target=run, name='evidence-lease-sweeper', daemon=True).start()
        return stop
