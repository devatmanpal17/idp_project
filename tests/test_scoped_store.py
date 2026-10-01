import tempfile
import unittest
import json
import random
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine, text
from ml.rag_engine import RAGEngine
from ml.scoped_store import unblob
from ml.answer_cache import cosine
from backend.models import AskRequest
from backend.routes import rag as routes
from backend.routes import vectors as vector_routes


class FakeEmbed:
    model = 'scoped-test'
    def __init__(self): self.calls = 0
    def embed(self, texts):
        self.calls += 1
        return [[float(len(value) % 7 + 1), 2.0, 3.0] for value in texts]


class ScopedStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.db = create_engine(f'sqlite:///{(root / "state.db").as_posix()}')
        self.embed = FakeEmbed()
        self.rag = RAGEngine(root / 'chroma', state_engine=self.db, embeddings=self.embed)
        self.learner, self.video = 'learner-1', 'youtube:test123'
        self.cues = [{'start': float(i), 'end': float(i + 1),
                      'text': f'Lesson step {i} explains a unique observation in detail.'}
                     for i in range(12)]

    def tearDown(self):
        self.db.dispose()
        self.tmp.cleanup()

    def test_seal_observe_micro_then_macro_and_reconcile(self):
        first = self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        self.assertGreater(first['sealed_added'], 1)
        self.assertEqual(self.embed.calls, 1)  # macro and micros embedded in one batch
        self.assertEqual(self.rag.scoped.retrieve(self.learner, self.video, 'lesson'), [])
        calls = self.embed.calls
        self.assertEqual(self.rag.scoped.seal(self.learner, self.video, self.cues, 12)['sealed_added'], 0)
        self.assertEqual(self.embed.calls, calls)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 5, 'wall_ms': 5000, 'rate': 1}])
        partial = self.rag.scoped.retrieve(self.learner, self.video, 'lesson')
        self.assertTrue(partial)
        self.assertEqual(self.rag.retrieve('lesson'), [])
        self.assertTrue(all(len(row['snippet'].split()) <= 50 for row in partial))
        with self.assertRaisesRegex(ValueError, 'batch_seq'):
            self.rag.scoped.intervals(self.learner, self.video, 1, [])
        self.rag.scoped.intervals(self.learner, self.video, 2,
            [{'start': 5, 'end': 12, 'wall_ms': 7000, 'rate': 1}])
        full = self.rag.scoped.retrieve(self.learner, self.video, 'lesson')
        self.assertTrue(any(len(row['snippet'].split()) > 50 for row in full))
        self.assertEqual(self.embed.calls, calls + 2)  # query cache resets on promotion
        with self.db.connect() as db:
            row = db.execute(text("SELECT chroma_id,vector FROM scoped_chunks WHERE state='ACTIVE' LIMIT 1")).first()
        stored = row[1]
        chroma = self.rag.collection.get(ids=[row[0]], include=['embeddings'])['embeddings'][0]
        self.assertTrue(all(abs(a - b) < 1e-6 for a, b in zip(chroma, unblob(stored))))
        self.rag.collection.delete(ids=[row[0]])
        self.rag.scoped.recover()
        self.assertIn(row[0], self.rag.collection.get(include=[])['ids'])

    def test_seal_retry_reuses_completed_embedding_batches(self):
        original = self.embed.embed
        seen = []
        def interrupt_second_batch(texts):
            seen.extend(texts)
            if len(seen) > 1:
                raise OSError('simulated interruption')
            return original(texts)
        with patch.dict('os.environ', {'F1_EMBED_BATCH_SIZE': '1'}), \
             patch.object(self.embed, 'embed', side_effect=interrupt_second_batch):
            with self.assertRaisesRegex(OSError, 'interruption'):
                self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        with self.db.connect() as db:
            checkpointed = db.execute(text('SELECT COUNT(*) FROM scoped_vector_blobs')).scalar_one()
        self.assertEqual(checkpointed, 1)
        calls = self.embed.calls
        with patch.dict('os.environ', {'F1_EMBED_BATCH_SIZE': '1'}):
            result = self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        self.assertGreater(result['sealed_added'], 0)
        self.assertEqual(self.embed.calls - calls, len(set(
            row['hash'] for row in self.rag.scoped._chunks(self.cues))) - 1)

    def test_implausible_interval_does_not_promote(self):
        self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        result = self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 12, 'wall_ms': 100, 'rate': 1}])
        self.assertEqual(result['promoted'], 0)
        self.assertEqual(result['rejected'], ['implausible_media_speed'])

    def test_offset_reupload_reuses_vectors_and_transfers_only_observed_coverage(self):
        source_cues = [{'start': float(i), 'end': float(i + 1),
                        'text': f'Unique lecture item {i} explains the copper circuit behavior.'}
                       for i in range(30)]
        self.rag.scoped.seal(self.learner, self.video, source_cues, 30)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 15, 'wall_ms': 15000, 'rate': 1}])
        before = self.embed.calls
        shifted = [{**cue, 'start': cue['start'] + 37, 'end': cue['end'] + 37}
                   for cue in source_cues]
        result = self.rag.scoped.seal(self.learner, 'youtube:reupload', shifted, 67)
        self.assertGreater(result['vectors_reused'], 0)
        self.assertEqual(self.embed.calls, before)
        with self.db.connect() as db:
            transferred = db.execute(text("""SELECT COUNT(*) FROM scoped_chunks WHERE
                video_key='youtube:reupload' AND provenance='transferred' AND state='ACTIVE'""")).scalar_one()
            unobserved = db.execute(text("""SELECT COUNT(*) FROM scoped_chunks WHERE
                video_key='youtube:reupload' AND t_start>=52000 AND state='SEALED'""")).scalar_one()
        self.assertGreater(transferred, 0)
        self.assertGreater(unobserved, 0)

    def test_different_wording_does_not_transfer(self):
        self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 12, 'wall_ms': 12000, 'rate': 1}])
        other = [{**cue, 'text': f'Different narrative about botanical specimen number {i}.'}
                 for i, cue in enumerate(self.cues)]
        self.rag.scoped.seal(self.learner, 'youtube:unrelated', other, 12)
        with self.db.connect() as db:
            count = db.execute(text("""SELECT COUNT(*) FROM scoped_chunks WHERE
                video_key='youtube:unrelated' AND state='ACTIVE'""")).scalar_one()
        self.assertEqual(count, 0)

    def test_scoped_quiz_lease_hides_aligned_copy_and_restores(self):
        source_cues = [{'start': float(i), 'end': float(i + 1),
                        'text': f'Original circuit lecture point number {i} and copper behavior.'}
                       for i in range(20)]
        self.rag.scoped.seal(self.learner, self.video, source_cues, 20)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 20, 'wall_ms': 20000, 'rate': 1}])
        shifted = [{**cue, 'start': cue['start'] + 37, 'end': cue['end'] + 37}
                   for cue in source_cues]
        self.rag.scoped.seal(self.learner, 'youtube:copy', shifted, 57)
        with self.db.connect() as db:
            source = db.execute(text("""SELECT chroma_id FROM scoped_chunks WHERE
                video_key=:video AND state='ACTIVE' AND granularity='micro' LIMIT 1"""),
                {'video': self.video}).scalar_one()
            copy_before = db.execute(text("""SELECT COUNT(*) FROM scoped_chunks WHERE
                video_key='youtube:copy' AND state='ACTIVE'""")).scalar_one()
        self.assertGreater(copy_before, 0)
        self.rag.leases.open_scoped('scoped-quiz', self.learner, self.video,
                                    [{'citations': [source]}])
        with self.db.connect() as db:
            hidden = set(db.execute(text("SELECT chroma_id FROM scoped_chunks WHERE state='DEMOTED'")).scalars())
            hidden_text = db.execute(text("SELECT content FROM scoped_chunks WHERE chroma_id=:id"),
                                     {'id': source}).scalar_one()
        with self.assertRaisesRegex(ValueError, 'locked'):
            self.rag.ingest_document(hidden_text, 'Bypass', 'Copied page')
        for index in range(200):
            found = self.rag.scoped.retrieve(self.learner, self.video,
                                             f'question {index} about the circuit', top_k=5)
            self.assertFalse(hidden.intersection(item['chunk_id'] for item in found))
        with self.db.connect() as db:
            copy_during = db.execute(text("""SELECT COUNT(*) FROM scoped_chunks WHERE
                video_key='youtube:copy' AND state='ACTIVE'""")).scalar_one()
        self.assertLess(copy_during, copy_before)
        self.rag.leases.close('scoped-quiz')
        with self.db.connect() as db:
            copy_after = db.execute(text("""SELECT COUNT(*) FROM scoped_chunks WHERE
                video_key='youtube:copy' AND state='ACTIVE'""")).scalar_one()
        self.assertEqual(copy_after, copy_before)

    def test_new_copy_sealed_during_quiz_stays_locked_until_close(self):
        source = [{'start': float(i), 'end': float(i + 1),
                   'text': f'Original circuit lecture point number {i} and copper behavior.'}
                  for i in range(20)]
        self.rag.scoped.seal(self.learner, self.video, source, 20)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 20, 'wall_ms': 20000, 'rate': 1}])
        with self.db.connect() as db:
            cited = db.execute(text("""SELECT chroma_id FROM scoped_chunks WHERE
                video_key=:video AND state='ACTIVE' AND granularity='micro' LIMIT 1"""),
                {'video': self.video}).scalar_one()
        lease = self.rag.leases.open_scoped('new-copy-quiz', self.learner, self.video,
                                           [{'citations': [cited]}])
        self.assertEqual(self.rag.leases.open_scoped('new-copy-quiz', self.learner,
            self.video, [{'citations': [cited]}]), lease)
        shifted = [{**cue, 'start': cue['start'] + 37, 'end': cue['end'] + 37}
                   for cue in source]
        self.rag.scoped.seal(self.learner, 'youtube:newcopy', shifted, 57)
        with self.db.connect() as db:
            rows = db.execute(text("""SELECT state,demote_refcount FROM scoped_chunks
                WHERE video_key='youtube:newcopy'""")).all()
        self.assertTrue(rows)
        self.assertTrue(all(state != 'ACTIVE' and held > 0 for state, held in rows))
        with self.assertRaisesRegex(ValueError, 'open quiz'):
            self.rag.scoped.seal(self.learner, self.video,
                [{**cue, 'text': cue['text'] + ' changed'} for cue in source], 20)
        self.rag.leases.close('new-copy-quiz')
        with self.db.connect() as db:
            transferred = db.execute(text("""SELECT COUNT(*) FROM scoped_chunks WHERE
                video_key='youtube:newcopy' AND state='ACTIVE'""")).scalar_one()
        self.assertGreater(transferred, 0)

    def test_scoped_answer_cache_hit_avoids_model_and_embedding(self):
        self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 12, 'wall_ms': 12000, 'rate': 1}])
        req = AskRequest(question='explain the lesson', source_type='video',
            learner_key=self.learner, video_key=self.video, top_k=2)
        with patch.object(routes, 'rag_engine', self.rag), patch.object(
            routes.llm_service, 'answer_with_rag', return_value='The lesson explains observations.') as answer:
            first = routes.ask_lesson(req)
            calls = self.embed.calls
            self.assertEqual(routes.ask_lesson(req), first)
            self.assertEqual(self.embed.calls, calls)
            self.assertEqual(answer.call_count, 1)

    def test_cache_mutation_rules_match_random_exact_top_three(self):
        rng = random.Random(207)
        corpus = [[rng.gauss(0, 1) for _ in range(6)] for _ in range(30)]
        incoming = [rng.gauss(0, 1) for _ in range(6)]
        entries = {}
        with self.db.begin() as db:
            for number in range(100):
                query = [rng.gauss(0, 1) for _ in range(6)]
                ranked = sorted(range(len(corpus)),
                    key=lambda index: (-cosine(query, corpus[index]), index))[:3]
                kth = cosine(query, corpus[ranked[-1]])
                key = f'property-{number}'
                entries[key] = (query, ranked, kth)
                db.execute(text('''INSERT INTO answer_cache VALUES
                    (:key,'property',0,:query,3,:kth,:ids,'{}','now')'''),
                    {'key': key, 'query': json.dumps(query), 'kth': kth,
                     'ids': json.dumps([str(index) for index in ranked])})
        self.rag.answer_cache.insert('property', [incoming])
        with self.db.connect() as db:
            remaining = set(db.execute(text("SELECT key FROM answer_cache WHERE scope='property'")).scalars())
        expected = {key for key, (query, _, kth) in entries.items()
                    if cosine(query, incoming) < kth}
        self.assertEqual(remaining, expected)
        removed = {'7'}
        self.rag.answer_cache.remove('property', removed)
        with self.db.connect() as db:
            remaining = set(db.execute(text("SELECT key FROM answer_cache WHERE scope='property'")).scalars())
        self.assertEqual(remaining, {key for key in expected
            if not removed.intersection(str(index) for index in entries[key][1])})
        self.rag.answer_cache.insert('property', [[1.0] * 7])
        with self.db.connect() as db:
            self.assertEqual(db.execute(text("SELECT COUNT(*) FROM answer_cache WHERE scope='property'")).scalar_one(), 0)

    def test_changed_caption_revision_removes_old_evidence_and_observation(self):
        self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 12, 'wall_ms': 12000, 'rate': 1}])
        self.assertTrue(self.rag.scoped.retrieve(self.learner, self.video, 'lesson'))
        changed = [{**cue, 'text': cue['text'].replace('Lesson', 'Changed')}
                   for cue in self.cues]
        self.rag.scoped.seal(self.learner, self.video, changed, 12)
        self.assertEqual(self.rag.scoped.retrieve(self.learner, self.video, 'lesson'), [])
        with self.db.connect() as db:
            scope = db.execute(text("""SELECT intervals_json,last_seq FROM scoped_videos WHERE
                learner_key=:learner AND video_key=:video"""),
                {'learner': self.learner, 'video': self.video}).first()
        self.assertEqual(scope[0], '[]')
        self.assertEqual(scope[1], -1)

    def test_scoped_http_route_functions_use_only_active_chunks(self):
        seal = vector_routes.SealRequest(learner_key=self.learner, video_key=self.video,
            cues=self.cues, duration=12)
        observed = vector_routes.ScopedIntervalsRequest(learner_key=self.learner,
            video_key=self.video, batch_seq=1,
            intervals=[{'start': 0, 'end': 5, 'wall_ms': 5000, 'rate': 1}])
        contexts = []
        def answer(_question, chunks, *_args, **_kwargs):
            contexts.extend(chunks)
            return 'An answer from observed material.'
        with patch.object(vector_routes, 'rag_engine', self.rag), \
             patch.object(routes, 'rag_engine', self.rag), \
             patch.object(routes.llm_service, 'answer_with_rag', side_effect=answer):
            vector_routes.seal_scoped(seal)
            vector_routes.scoped_intervals(observed)
            response = routes.ask_lesson(AskRequest(question='explain step', source_type='video',
                learner_key=self.learner, video_key=self.video))
        self.assertEqual(response['answer'], 'An answer from observed material.')
        self.assertTrue(contexts)
        self.assertTrue(all(len(chunk['snippet'].split()) <= 50 for chunk in contexts))

    def test_trimmed_intro_inserted_segment_and_middle_clip_alignment(self):
        source = [{'start': float(i), 'end': float(i + 1),
                   'text': f'Chapter {i} describes a distinct copper coil procedure.'}
                  for i in range(30)]
        self.rag.scoped.seal(self.learner, self.video, source, 30)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 30, 'wall_ms': 30000, 'rate': 1}])
        trimmed = [{**cue, 'start': cue['start'] - 5, 'end': cue['end'] - 5}
                   for cue in source[5:]]
        self.rag.scoped.seal(self.learner, 'youtube:trimmed', trimmed, 25)
        clip = [{**cue, 'start': cue['start'] - 10, 'end': cue['end'] - 10}
                for cue in source[10:20]]
        self.rag.scoped.seal(self.learner, 'youtube:clip', clip, 10)
        inserted = source[:15] + [{'start': 15.0, 'end': 105.0,
            'text': 'A newly inserted advertisement with unrelated botanical wording.'}] + [
            {**cue, 'start': cue['start'] + 90, 'end': cue['end'] + 90} for cue in source[15:]]
        self.rag.scoped.seal(self.learner, 'youtube:inserted', inserted, 120)
        with self.db.connect() as db:
            for video in ('youtube:trimmed', 'youtube:clip', 'youtube:inserted'):
                count = db.execute(text("""SELECT COUNT(*) FROM scoped_chunks WHERE
                    video_key=:video AND state='ACTIVE'"""), {'video': video}).scalar_one()
                self.assertGreater(count, 0)
            ad = db.execute(text("""SELECT COUNT(*) FROM scoped_chunks WHERE
                video_key='youtube:inserted' AND content LIKE '%advertisement%'
                AND state='ACTIVE'""")).scalar_one()
        self.assertEqual(ad, 0)
