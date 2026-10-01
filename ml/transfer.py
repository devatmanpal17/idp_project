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
    for cue_index, cue in enumerate(cues):
        parts = cue['content'].split()
        for part in parts:
            word = ''.join(char for char in part if char.isalnum())
            if word:
                # Captions provide cue timing, not word timing. Require the full
                # source cue even when only some of its words match a clip.
                words.append((word, cue['t_start'], cue['t_end'], cue_index))
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
        target_ranges = {}
        for index, word in enumerate(target_words):
            target_ranges.setdefault(word[3], [index, index])[1] = index
        for block in matcher.get_matching_blocks():
            if block.size < self.min_block_words:
                continue
            matched_source = source_words[block.a:block.a + block.size]
            matched_target = target_words[block.b:block.b + block.size]
            source_start = min(word[1] for word in matched_source)
            source_end = max(word[2] for word in matched_source)
            target_start = min(word[1] for word in matched_target)
            target_end = max(word[2] for word in matched_target)
            if source_end <= source_start or target_end <= target_start:
                continue
            segments = {}
            for source_word, target_word in zip(matched_source, matched_target):
                cue_index = target_word[3]
                first, last = target_ranges[cue_index]
                segment = segments.setdefault(cue_index, {
                    'cue_index': cue_index, 'target_start': target_word[1],
                    'target_end': target_word[2], 'source_spans': set(),
                    'complete': first >= block.b and last < block.b + block.size})
                segment['source_spans'].add((source_word[1], source_word[2]))
            for segment in segments.values():
                segment['source_spans'] = sorted(segment['source_spans'])
            blocks.append({'source_start': source_start, 'source_end': source_end,
                           'target_start': target_start, 'target_end': target_end,
                           'words': block.size, 'confidence': 1.0,
                           'segments': list(segments.values())})
        self.stats['aligned_blocks'] += len(blocks)
        return blocks

    def _transfer(self, learner, source, target):
        with self.store.lock:
            blocks = self.align(learner, source, target)
            if not blocks:
                return 0
            mapped_cues = {segment['cue_index']: segment for block in blocks
                           if block['confidence'] >= self.min_conf
                           for segment in block['segments'] if segment['complete']}
            target_cues = self._cues(learner, target)
            with self.store.engine.connect() as db:
                scope = self.store._scope(db, learner, source)
                rows = [dict(row) for row in db.execute(text("""SELECT * FROM scoped_chunks
                    WHERE learner_key=:learner AND video_key=:target AND state='SEALED'
                    AND embed_model=:model"""),
                    {'learner': learner, 'target': target,
                     'model': self.store.rag.model_version}).mappings()]
                leased = db.execute(text("""SELECT t_start,t_end FROM scoped_chunks WHERE
                    learner_key=:learner AND video_key=:source AND demote_refcount>0"""),
                    {'learner': learner, 'source': source}).all()
            if not scope:
                return 0
            observed = json.loads(scope['intervals_json'])
            promoted = 0
            for row in rows:
                required_cues = [index for index, cue in enumerate(target_cues)
                                 if cue['t_start'] < row['t_end'] and row['t_start'] < cue['t_end']]
                if not required_cues or any(index not in mapped_cues for index in required_cues):
                    continue
                source_spans = {span for index in required_cues
                                for span in mapped_cues[index]['source_spans']}
                if any(coverage(start, end, observed) < 1.0 or
                       any(left < end and start < right for left, right in leased)
                       for start, end in source_spans):
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
                        continue
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
