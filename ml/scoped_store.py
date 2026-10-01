"""Learner-scoped sealed micro/macro vectors and plausible rendered-interval ledger."""
from __future__ import annotations

import hashlib
import json
import math
import os
import struct
from datetime import datetime, timezone

from sqlalchemy import text

from .temporal import Caption, temporal_chunks


def stamp():
    return datetime.now(timezone.utc).isoformat()


def normal(value):
    return ' '.join(value.split())


def blob(vector):
    if not vector or any(isinstance(value, bool) or not isinstance(value, (int, float))
                         or not math.isfinite(value) for value in vector):
        raise ValueError('Embedder returned an invalid vector.')
    try:
        raw = struct.pack(f'<{len(vector)}f', *vector)
    except (OverflowError, struct.error) as exc:
        raise ValueError('Embedding components must fit finite float32 values.') from exc
    if any(not math.isfinite(value) for value in unblob(raw)):
        raise ValueError('Embedding components must fit finite float32 values.')
    return raw


def unblob(raw):
    return list(struct.unpack(f'<{len(raw)//4}f', raw))


def merge(intervals):
    out = []
    for start, end in sorted(intervals, key=lambda pair: (pair[0], pair[1])):
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return out


def coverage(start, end, intervals):
    if end <= start:
        return 0.0
    return sum(max(0, min(end, right) - max(start, left)) for left, right in intervals) / (end - start)


class ScopedStore:
    def __init__(self, rag):
        self.rag = rag
        self.engine = rag.vectors.engine
        self.lock = rag._lock
        self.enabled = os.getenv('F1_ENABLED', 'true').lower() == 'true'
        self.threshold = float(os.getenv('F1_COVERAGE_THRESHOLD', '1.0'))
        self.micro_words = int(os.getenv('E_MICRO_WORDS', '50'))
        self.macro_words = int(os.getenv('E_MACRO_WORDS', '220'))
        with self.engine.begin() as db:
            # Checkpoint each completed batch so a resumed seal never repeats inference.
            db.execute(text("""CREATE TABLE IF NOT EXISTS scoped_vector_blobs (
                content_hash TEXT NOT NULL, embed_model TEXT NOT NULL, vector BLOB NOT NULL,
                PRIMARY KEY(content_hash,embed_model))"""))
            db.execute(text("""CREATE TABLE IF NOT EXISTS scoped_videos (
                learner_key TEXT NOT NULL, video_key TEXT NOT NULL,
                duration_ms INTEGER NOT NULL, last_seq INTEGER NOT NULL DEFAULT -1,
                promotion_seq INTEGER NOT NULL DEFAULT 0, intervals_json TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY (learner_key,video_key))"""))
            db.execute(text("""CREATE TABLE IF NOT EXISTS scoped_chunks (
                learner_key TEXT NOT NULL, video_key TEXT NOT NULL, chunk_id TEXT NOT NULL,
                chroma_id TEXT NOT NULL UNIQUE, granularity TEXT NOT NULL,
                parent_id TEXT, t_start INTEGER NOT NULL, t_end INTEGER NOT NULL,
                content TEXT NOT NULL, content_hash TEXT NOT NULL, embed_model TEXT NOT NULL,
                vector BLOB NOT NULL, state TEXT NOT NULL, promotion_seq INTEGER NOT NULL DEFAULT 0,
                demote_refcount INTEGER NOT NULL DEFAULT 0, provenance TEXT NOT NULL DEFAULT 'observed',
                source_video_key TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY (learner_key,video_key,chunk_id))"""))
            db.execute(text("""CREATE TABLE IF NOT EXISTS scoped_interval_batches (
                learner_key TEXT NOT NULL, video_key TEXT NOT NULL, batch_seq INTEGER NOT NULL,
                accepted INTEGER NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(learner_key,video_key,batch_seq))"""))
            db.execute(text("""CREATE TABLE IF NOT EXISTS scoped_cues (
                learner_key TEXT NOT NULL, video_key TEXT NOT NULL, cue_index INTEGER NOT NULL,
                t_start INTEGER NOT NULL, t_end INTEGER NOT NULL, content TEXT NOT NULL,
                PRIMARY KEY(learner_key,video_key,cue_index))"""))
            db.execute(text("""CREATE TABLE IF NOT EXISTS scoped_revisions (
                learner_key TEXT NOT NULL, video_key TEXT NOT NULL, revision TEXT NOT NULL,
                PRIMARY KEY(learner_key,video_key))"""))
            db.execute(text("""CREATE TABLE IF NOT EXISTS scoped_interval_rejections (
                learner_key TEXT NOT NULL, video_key TEXT NOT NULL, batch_seq INTEGER NOT NULL,
                reason TEXT NOT NULL, created_at TEXT NOT NULL)"""))

    def _scope(self, db, learner, video):
        return db.execute(text("""SELECT * FROM scoped_videos
            WHERE learner_key=:learner AND video_key=:video"""),
            {'learner': learner, 'video': video}).mappings().first()

    def _chunks(self, cues):
        clean, _ = temporal_chunks([Caption(start_ms=int(c['start'] * 1000),
            end_ms=int(c['end'] * 1000), text=c['text']) for c in cues])
        macros, current = [], []
        for cue in clean:
            if current and sum(len(item['text'].split()) for item in current) + len(cue['text'].split()) > self.macro_words:
                macros.append(current); current = []
            current.append(cue)
        if current:
            macros.append(current)
        result = []
        for macro in macros:
            parent = self._make_chunk(macro, 'macro', None)
            result.append(parent)
            micro = []
            for cue in macro:
                if micro and sum(len(item['text'].split()) for item in micro) + len(cue['text'].split()) > self.micro_words:
                    result.append(self._make_chunk(micro, 'micro', parent))
                    micro = []
                micro.append(cue)
            if micro:
                result.append(self._make_chunk(micro, 'micro', parent))
        return result

    def _make_chunk(self, cues, granularity, parent):
        value = normal(' '.join(c['text'] for c in cues))
        return {'granularity': granularity, 'parent': parent,
                'start': min(c['start_ms'] for c in cues),
                'end': max(c['end_ms'] for c in cues),
                'text': value, 'hash': hashlib.sha256(value.encode()).hexdigest()}

    def seal(self, learner, video, cues, duration):
        if not video.startswith('youtube:'):
            raise ValueError('video_key must start with youtube:')
        pieces = self._chunks(cues)
        if not pieces:
            raise ValueError('No indexable caption cues.')
        duration_ms = int(duration * 1000)
        if duration_ms <= 0:
            raise ValueError('Video duration must be positive.')
        with self.lock:
            revision = hashlib.sha256(json.dumps([cues, duration_ms], sort_keys=True).encode()).hexdigest()
            revision_changed = False
            revoked = []
            with self.engine.begin() as db:
                existing = self._scope(db, learner, video)
                old_revision = db.execute(text("""SELECT revision FROM scoped_revisions WHERE
                    learner_key=:learner AND video_key=:video"""),
                    {'learner': learner, 'video': video}).scalar()
                old_model = db.execute(text("""SELECT 1 FROM scoped_chunks WHERE
                    learner_key=:learner AND video_key=:video AND embed_model<>:model LIMIT 1"""),
                    {'learner': learner, 'video': video, 'model': self.rag.model_version}).scalar()
                track_changed = bool(existing and old_revision and old_revision != revision)
                if track_changed or old_model:
                    if hasattr(self.rag, 'leases') and self.rag.leases.has_open(f'scoped:{learner}|{video}'):
                        raise ValueError('Submit or abandon the open quiz before changing this caption track.')
                    revision_changed = True
                    ids = db.execute(text("""SELECT chroma_id FROM scoped_chunks WHERE
                        learner_key=:learner AND video_key=:video"""),
                        {'learner': learner, 'video': video}).scalars().all()
                    if ids:
                        self.rag.collection.delete(ids=ids)
                    db.execute(text("DELETE FROM scoped_chunks WHERE learner_key=:learner AND video_key=:video"),
                               {'learner': learner, 'video': video})
                    db.execute(text("DELETE FROM scoped_cues WHERE learner_key=:learner AND video_key=:video"),
                               {'learner': learner, 'video': video})
                    if track_changed:
                        # The reset sequence belongs to the new caption revision.
                        db.execute(text("DELETE FROM scoped_interval_batches WHERE learner_key=:learner AND video_key=:video"),
                                   {'learner': learner, 'video': video})
                        db.execute(text("""UPDATE scoped_videos SET intervals_json='[]',last_seq=-1,
                            promotion_seq=0,duration_ms=:duration
                            WHERE learner_key=:learner AND video_key=:video"""),
                            {'learner': learner, 'video': video, 'duration': duration_ms})
                        # A source revision also invalidates observation transferred from it.
                        revoked = db.execute(text("""SELECT chroma_id,video_key FROM scoped_chunks
                            WHERE learner_key=:learner AND source_video_key=:video
                            AND provenance='transferred'"""),
                            {'learner': learner, 'video': video}).all()
                        db.execute(text("""UPDATE scoped_chunks SET state='SEALED',
                            provenance='observed',source_video_key=NULL,promotion_seq=0,updated_at=:now
                            WHERE learner_key=:learner AND source_video_key=:video
                            AND provenance='transferred'"""),
                            {'learner': learner, 'video': video, 'now': stamp()})
                if not existing:
                    db.execute(text("""INSERT INTO scoped_videos
                        (learner_key,video_key,duration_ms) VALUES (:learner,:video,:duration)"""),
                        {'learner': learner, 'video': video, 'duration': duration_ms})
                db.execute(text("""INSERT INTO scoped_revisions VALUES (:learner,:video,:revision)
                    ON CONFLICT(learner_key,video_key) DO UPDATE SET revision=excluded.revision"""),
                    {'learner': learner, 'video': video, 'revision': revision})
                cues_present = db.execute(text("""SELECT COUNT(*) FROM scoped_cues WHERE
                    learner_key=:learner AND video_key=:video"""),
                    {'learner': learner, 'video': video}).scalar()
                if not cues_present:
                    for index, cue in enumerate(cues):
                        db.execute(text("""INSERT INTO scoped_cues VALUES
                            (:learner,:video,:index,:start,:end,:content)"""),
                            {'learner': learner, 'video': video, 'index': index,
                             'start': int(cue['start'] * 1000), 'end': int(cue['end'] * 1000),
                             'content': normal(cue['text'])})
            if revision_changed:
                if revoked:
                    self.rag.collection.delete(ids=[row[0] for row in revoked])
                if hasattr(self.rag, 'answer_cache'):
                    self.rag.answer_cache.bump_epoch(f'scoped:{learner}|{video}')
                    for affected_video in {row[1] for row in revoked}:
                        self.rag.answer_cache.bump_epoch(f'scoped:{learner}|{affected_video}')
                self.rag.invalidate_cache()
            prepared = []
            known_vectors = {}
            missing = {}
            for piece in pieces:
                parent = piece['parent']
                parent_id = parent.get('id') if parent else None
                identity = f"{video}|{piece['granularity']}|{piece['start']}|{piece['end']}|{piece['hash']}"
                piece['id'] = hashlib.sha256(identity.encode()).hexdigest()[:24]
                with self.engine.connect() as db:
                    found = db.execute(text("""SELECT 1 FROM scoped_chunks WHERE
                        learner_key=:learner AND video_key=:video AND chunk_id=:id"""),
                        {'learner': learner, 'video': video, 'id': piece['id']}).scalar()
                    old_vector = db.execute(text("""SELECT vector FROM scoped_vector_blobs WHERE
                        content_hash=:hash AND embed_model=:model UNION ALL
                        SELECT vector FROM scoped_chunks WHERE
                        content_hash=:hash AND embed_model=:model LIMIT 1"""),
                        {'hash': piece['hash'], 'model': self.rag.model_version}).scalar()
                if found:
                    continue
                if old_vector is not None:
                    known_vectors[piece['hash']] = old_vector
                else:
                    missing.setdefault(piece['hash'], piece['text'])
                prepared.append((piece, parent_id, old_vector is not None))
            batch_size = max(1, int(os.getenv('F1_EMBED_BATCH_SIZE', '32')))
            with self.engine.connect() as db:
                sample = db.execute(text("""SELECT vector FROM scoped_vector_blobs
                    WHERE embed_model=:model LIMIT 1"""), {'model': self.rag.model_version}).scalar()
            dimension = len(sample) // 4 if sample else None
            unknown = list(missing.items())
            for offset in range(0, len(unknown), batch_size):
                batch = unknown[offset:offset + batch_size]
                vectors = self.rag.embeddings.embed([content for _, content in batch])
                if len(vectors) != len(batch):
                    raise ValueError('Embedder returned an incomplete batch.')
                with self.engine.begin() as db:
                    for (content_hash, _), vector in zip(batch, vectors):
                        raw = blob(vector)
                        if dimension is not None and len(vector) != dimension:
                            raise ValueError('Embedder returned inconsistent vector dimensions.')
                        dimension = len(vector)
                        known_vectors[content_hash] = raw
                        db.execute(text('''INSERT OR IGNORE INTO scoped_vector_blobs
                            VALUES (:hash,:model,:vector)'''),
                            {'hash': content_hash, 'model': self.rag.model_version, 'vector': raw})
            added = 0
            reused = len(prepared) - len(unknown)
            with self.engine.begin() as db:
                for piece, parent_id, _ in prepared:
                    vector = known_vectors[piece['hash']]
                    chroma_id = hashlib.sha256(f'{learner}|{piece["id"]}'.encode()).hexdigest()[:32]
                    db.execute(text("""INSERT INTO scoped_chunks
                        (learner_key,video_key,chunk_id,chroma_id,granularity,parent_id,
                         t_start,t_end,content,content_hash,embed_model,vector,state,created_at,updated_at)
                        VALUES (:learner,:video,:id,:chroma,:granularity,:parent,:start,:end,
                                :content,:hash,:model,:vector,'SEALED',:now,:now)"""),
                        dict(learner=learner, video=video, id=piece['id'], chroma=chroma_id,
                             granularity=piece['granularity'], parent=parent_id,
                             start=piece['start'], end=piece['end'], content=piece['text'],
                             hash=piece['hash'], model=self.rag.model_version,
                             vector=vector, now=stamp()))
                    added += 1
            if hasattr(self.rag, 'leases'):
                self.rag.leases.refresh_scoped(learner)
            self.promote(learner, video)
            for affected_video in {row[1] for row in revoked}:
                self.promote(learner, affected_video)
            if hasattr(self, 'transfer'):
                self.transfer.on_seal(learner, video)
            with self.engine.connect() as db:
                last_seq = self._scope(db, learner, video)['last_seq']
            return {'sealed_added': added, 'vectors_reused': reused,
                    'revision': revision,
                    'last_batch_seq': last_seq,
                    'counts': self.status(learner, video)['counts']}

    def intervals(self, learner, video, seq, intervals, revision=None):
        with self.lock:
            with self.engine.connect() as db:
                previous = self._scope(db, learner, video)
            if not previous:
                raise ValueError('Seal this video before uploading intervals.')
            if revision is not None:
                with self.engine.connect() as db:
                    current_revision = db.execute(text("""SELECT revision FROM scoped_revisions
                        WHERE learner_key=:learner AND video_key=:video"""),
                        {'learner': learner, 'video': video}).scalar()
                if revision != current_revision:
                    raise ValueError('Caption revision changed; seal again before uploading intervals.')
            if seq <= previous['last_seq']:
                with self.engine.begin() as db:
                    db.execute(text("""INSERT INTO scoped_interval_rejections VALUES
                        (:learner,:video,:seq,'non_monotonic_batch_seq',:now)"""),
                        {'learner': learner, 'video': video, 'seq': seq, 'now': stamp()})
                raise ValueError('batch_seq must increase monotonically.')
            with self.engine.begin() as db:
                scope = self._scope(db, learner, video)
                valid, rejected = [], []
                for item in intervals:
                    start = max(0, min(scope['duration_ms'], int(item['start'] * 1000)))
                    end = max(0, min(scope['duration_ms'], int(item['end'] * 1000)))
                    if end <= start:
                        rejected.append('empty_or_outside_video'); continue
                    if (end - start) > item['wall_ms'] * item['rate'] * 1.1 + 500:
                        rejected.append('implausible_media_speed'); continue
                    valid.append((start, end))
                combined = merge(json.loads(scope['intervals_json']) + valid)
                db.execute(text("""UPDATE scoped_videos SET last_seq=:seq,intervals_json=:intervals
                    WHERE learner_key=:learner AND video_key=:video"""),
                    dict(seq=seq, intervals=json.dumps(combined), learner=learner, video=video))
                db.execute(text("""INSERT INTO scoped_interval_batches VALUES
                    (:learner,:video,:seq,:accepted,:reason,:created)"""),
                    dict(learner=learner, video=video, seq=seq, accepted=len(valid),
                         reason=json.dumps(rejected), created=stamp()))
            promoted = self.promote(learner, video)
            if hasattr(self, 'transfer'):
                self.transfer.on_observation(learner, video)
            return {'accepted': len(valid), 'rejected': rejected, 'promoted': promoted,
                    'counts': self.status(learner, video)['counts']}

    def promote(self, learner, video):
        with self.lock:
            with self.engine.connect() as db:
                scope = self._scope(db, learner, video)
                if not scope:
                    return 0
                rows = db.execute(text("""SELECT * FROM scoped_chunks WHERE learner_key=:learner
                    AND video_key=:video AND state='SEALED' AND embed_model=:model"""),
                    {'learner': learner, 'video': video, 'model': self.rag.model_version}).mappings().all()
            observed = json.loads(scope['intervals_json'])
            promoted = 0
            for row in rows:
                required = 1.0 if row['granularity'] == 'micro' else self.threshold
                if coverage(row['t_start'], row['t_end'], observed) < required:
                    continue
                with self.engine.begin() as db:
                    changed = db.execute(text("""UPDATE scoped_chunks SET state='ACTIVE',updated_at=:now,
                        promotion_seq=(SELECT promotion_seq+1 FROM scoped_videos
                          WHERE learner_key=:learner AND video_key=:video)
                        WHERE learner_key=:learner AND video_key=:video AND chunk_id=:id
                        AND state='SEALED' AND demote_refcount=0"""),
                        dict(now=stamp(), learner=learner, video=video, id=row['chunk_id']))
                    if not changed.rowcount:
                        continue
                    db.execute(text("""UPDATE scoped_videos SET promotion_seq=promotion_seq+1
                        WHERE learner_key=:learner AND video_key=:video"""),
                        {'learner': learner, 'video': video})
                with self.engine.connect() as db:
                    row = db.execute(text("""SELECT * FROM scoped_chunks WHERE learner_key=:learner
                        AND video_key=:video AND chunk_id=:id"""),
                        {'learner': learner, 'video': video, 'id': row['chunk_id']}).mappings().one()
                self._upsert(row)
                if hasattr(self.rag, 'answer_cache'):
                    self.rag.answer_cache.insert(f'scoped:{learner}|{video}', [unblob(row['vector'])])
                promoted += 1
            if promoted:
                self.rag.invalidate_cache()
            return promoted

    def _upsert(self, row):
        if row['embed_model'] != self.rag.model_version:
            return
        self.rag.collection.upsert(ids=[row['chroma_id']], documents=[row['content']],
            embeddings=[unblob(row['vector'])], metadatas=[{
                'learner_key': row['learner_key'], 'video_key': row['video_key'],
                'chunk_id': row['chunk_id'], 'granularity': row['granularity'],
                'parent_id': row['parent_id'] or '', 't_start': row['t_start'],
                't_end': row['t_end'], 'promotion_seq': int(row['promotion_seq']),
                'source_type': 'video', 'topic': 'Current lesson',
                'scope_kind': 'scoped',
                'document_id': f"{row['learner_key']}|{row['video_key']}",
            }])

    def recover(self):
        with self.lock:
            with self.engine.connect() as db:
                rows = db.execute(text('SELECT * FROM scoped_chunks')).mappings().all()
            existing = set(self.rag.collection.get(include=[])['ids'])
            for row in rows:
                searchable = row['state'] == 'ACTIVE' and row['embed_model'] == self.rag.model_version
                if searchable and row['chroma_id'] not in existing:
                    self._upsert(row)
                elif not searchable and row['chroma_id'] in existing:
                    self.rag.collection.delete(ids=[row['chroma_id']])

    def status(self, learner, video):
        with self.engine.connect() as db:
            counts = dict(db.execute(text("""SELECT state,COUNT(*) FROM scoped_chunks
                WHERE learner_key=:learner AND video_key=:video GROUP BY state"""),
                {'learner': learner, 'video': video}).all())
        return {'learner_key': learner, 'video_key': video, 'counts': counts}

    def retrieve(self, learner, video, query, top_k=6, topic=None):
        from .answer_cache import cosine
        with self.lock:
            with self.engine.connect() as db:
                rows = [dict(row) for row in db.execute(text("""SELECT * FROM scoped_chunks
                    WHERE learner_key=:learner AND video_key=:video AND state='ACTIVE'
                    AND embed_model=:model"""),
                    {'learner': learner, 'video': video, 'model': self.rag.model_version}).mappings()]
            if not rows:
                return []
            query_text = normal(f'{topic or ""} {query}')
            key = json.dumps([self.rag.model_version, query_text])
            vector = self.rag.query_vector_cache.get(key)
            if vector is None:
                vector = self.rag.embeddings.embed([query_text])[0]
                self.rag.query_vector_cache.put(key, vector)
            by_id = {row['chunk_id']: row for row in rows}
            ranked = sorted(((cosine(vector, unblob(row['vector'])), row) for row in rows),
                            key=lambda item: (-item[0], item[1]['chunk_id']))
            chosen = []
            seen = set()
            for score, row in ranked:
                if row['granularity'] == 'micro' and row['parent_id'] in by_id:
                    row = by_id[row['parent_id']]
                    score = cosine(vector, unblob(row['vector']))
                if row['chunk_id'] in seen:
                    continue
                seen.add(row['chunk_id'])
                chosen.append({'chunk_id': row['chroma_id'], 'topic': topic or 'Current lesson',
                    'course': '', 'source': video, 'timestamp': str(row['t_start'] / 1000),
                    'snippet': row['content'], 'similarity': round(score, 4),
                    'distance': round(1.0 - score, 4), 'token_count': len(row['content'].split())})
                if len(chosen) >= top_k:
                    break
            return chosen
