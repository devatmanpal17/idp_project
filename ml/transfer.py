"""Transcript alignment transfers directly observed coverage between a learner's videos."""
from __future__ import annotations

import difflib
import hashlib
import json
import os

from sqlalchemy import text

from .scoped_store import coverage, stamp, unblob


def _tokens(cues):
    words = []
    for cue in cues:
        parts = cue['content'].casefold().split()
        duration = cue['t_end'] - cue['t_start']
        for index, part in enumerate(parts):
            word = ''.join(char for char in part if char.isalnum())
            if word:
                words.append((word, cue['t_start'] + duration * index / len(parts),
                              cue['t_start'] + duration * (index + 1) / len(parts)))
    return words


def _shingles(words, width=5):
    values = [item[0] for item in words]
    return {hashlib.sha256(' '.join(values[index:index + width]).encode()).digest()[:8]
            for index in range(max(0, len(values) - width + 1))}


class TransferEngine:
    def __init__(self, store):
        self.store = store
        self.candidate_jaccard = float(os.getenv('D_CANDIDATE_JACCARD', '0.15'))
        self.min_block_words = int(os.getenv('D_MIN_BLOCK_WORDS', '12'))
        self.min_conf = float(os.getenv('D_MIN_CONF', '0.9'))
        self.stats = {'candidates': 0, 'aligned_blocks': 0, 'promoted': 0}

    def _cues(self, learner, video):
        with self.store.engine.connect() as db:
            return [dict(row) for row in db.execute(text("""SELECT * FROM scoped_cues WHERE
                learner_key=:learner AND video_key=:video ORDER BY cue_index"""),
                {'learner': learner, 'video': video}).mappings()]

    def _other_videos(self, learner, video):
        with self.store.engine.connect() as db:
            return db.execute(text("""SELECT video_key FROM scoped_videos WHERE
                learner_key=:learner AND video_key<>:video"""),
                {'learner': learner, 'video': video}).scalars().all()

    def align(self, learner, source, target):
        source_words = _tokens(self._cues(learner, source))
        target_words = _tokens(self._cues(learner, target))
        source_shingles, target_shingles = _shingles(source_words), _shingles(target_words)
        if not source_shingles or not target_shingles:
            return []
        # Containment permits a short clip of a much longer lecture to qualify.
        score = len(source_shingles & target_shingles) / min(len(source_shingles), len(target_shingles))
        if score < self.candidate_jaccard:
            return []
        self.stats['candidates'] += 1
        matcher = difflib.SequenceMatcher(None, [word[0] for word in source_words],
                                          [word[0] for word in target_words], autojunk=False)
        blocks = []
        for block in matcher.get_matching_blocks():
            if block.size < self.min_block_words:
                continue
            source_start = source_words[block.a][1]
            source_end = source_words[block.a + block.size - 1][2]
            target_start = target_words[block.b][1]
            target_end = target_words[block.b + block.size - 1][2]
            if source_end <= source_start or target_end <= target_start:
                continue
            blocks.append({'source_start': source_start, 'source_end': source_end,
                           'target_start': target_start, 'target_end': target_end,
                           'words': block.size, 'confidence': 1.0})
        self.stats['aligned_blocks'] += len(blocks)
        return blocks

    def _transfer(self, learner, source, target):
        blocks = self.align(learner, source, target)
        if not blocks:
            return 0
        with self.store.lock:
            with self.store.engine.connect() as db:
                scope = self.store._scope(db, learner, source)
                rows = [dict(row) for row in db.execute(text("""SELECT * FROM scoped_chunks
                    WHERE learner_key=:learner AND video_key=:target AND state='SEALED'"""),
                    {'learner': learner, 'target': target}).mappings()]
                leased = db.execute(text("""SELECT t_start,t_end FROM scoped_chunks WHERE
                    learner_key=:learner AND video_key=:source AND state='DEMOTED'"""),
                    {'learner': learner, 'source': source}).all()
            observed = json.loads(scope['intervals_json'])
            promoted = 0
            for row in rows:
                for block in blocks:
                    if block['confidence'] < self.min_conf or row['t_start'] < block['target_start'] - 1 or row['t_end'] > block['target_end'] + 1:
                        continue
                    scale = (block['source_end'] - block['source_start']) / (block['target_end'] - block['target_start'])
                    mapped_start = block['source_start'] + (row['t_start'] - block['target_start']) * scale
                    mapped_end = block['source_start'] + (row['t_end'] - block['target_start']) * scale
                    if any(left < mapped_end and mapped_start < right for left, right in leased):
                        continue
                    required = 1.0 if row['granularity'] == 'micro' else self.store.threshold
                    if coverage(mapped_start, mapped_end, observed) < required:
                        continue
                    with self.store.engine.begin() as db:
                        changed = db.execute(text("""UPDATE scoped_chunks SET state='ACTIVE',
                            provenance='transferred',source_video_key=:source,updated_at=:now,
                            promotion_seq=(SELECT promotion_seq+1 FROM scoped_videos
                              WHERE learner_key=:learner AND video_key=:target)
                            WHERE learner_key=:learner AND video_key=:target AND chunk_id=:id
                            AND state='SEALED' AND demote_refcount=0"""),
                            {'source': source, 'now': stamp(), 'learner': learner,
                             'target': target, 'id': row['chunk_id']})
                        if not changed.rowcount:
                            break
                        db.execute(text("""UPDATE scoped_videos SET promotion_seq=promotion_seq+1
                            WHERE learner_key=:learner AND video_key=:target"""),
                            {'learner': learner, 'target': target})
                    with self.store.engine.connect() as db:
                        current = db.execute(text("""SELECT * FROM scoped_chunks WHERE
                            learner_key=:learner AND video_key=:target AND chunk_id=:id"""),
                            {'learner': learner, 'target': target, 'id': row['chunk_id']}).mappings().one()
                    self.store._upsert(current)
                    if hasattr(self.store.rag, 'answer_cache'):
                        self.store.rag.answer_cache.insert(f'scoped:{learner}|{target}', [unblob(row['vector'])])
                    promoted += 1
                    break
            if promoted:
                self.store.rag.invalidate_cache()
            self.stats['promoted'] += promoted
            return promoted

    def on_seal(self, learner, video):
        count = 0
        for other in self._other_videos(learner, video):
            count += self._transfer(learner, other, video)
            count += self._transfer(learner, video, other)
        return count

    def on_observation(self, learner, video):
        count = 0
        for other in self._other_videos(learner, video):
            count += self._transfer(learner, video, other)
        return count
