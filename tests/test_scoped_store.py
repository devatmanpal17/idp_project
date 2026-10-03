import tempfile
import unittest
import json
import random
import os
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine, text
from ml.rag_engine import RAGEngine, RAGConfigurationError
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

    def test_production_model_version_resolves_the_requested_tag(self):
        embedder = FakeEmbed()
        embedder.model = 'embeddinggemma:study'
        embedder.base_url = 'http://embedding.test'
        for name, expected in [('embeddinggemma:study', 'embeddinggemma:study:wanted'),
                               ('embeddinggemma:other', 'embeddinggemma:study:unresolved')]:
            with self.subTest(available_tag=name), patch.dict(os.environ, {'OLLAMA_EMBED_VERSION': embedder.model}), \
                 patch('ml.rag_engine.OllamaEmbeddings', return_value=embedder), \
                 patch('ml.rag_engine.urllib.request.urlopen') as request:
                request.return_value.__enter__.return_value.read.return_value = json.dumps({'models': [
                    {'name': 'embeddinggemma:old', 'digest': 'wrong'},
                    {'name': name, 'digest': 'wanted'}]}).encode()
                restarted = RAGEngine(Path(self.tmp.name) / 'chroma', state_engine=self.db)
                self.assertEqual(restarted.model_version, expected)

    def test_hosted_inventory_outage_cannot_recover_or_invalidate_persisted_vectors(self):
        # Existing temporal records are especially sensitive: recovery deletes
        # revisions whose embedding identity differs from the startup identity.
        from ml.temporal import Caption
        document = self.rag.vectors.register('https://demo.test/persist', 'Saved lesson',
            [Caption(start_ms=0, end_ms=1000, text='The saved evidence must survive a temporary outage.')])
        with patch.dict(os.environ, {'CHAI_REQUIRE_RESOLVED_EMBEDDING_MODEL': 'true'}), \
             patch('ml.rag_engine.urllib.request.urlopen', side_effect=OSError('temporary inventory outage')), \
             patch('ml.rag_engine.chromadb.PersistentClient') as chroma:
            with self.assertRaisesRegex(RAGConfigurationError, 'identity is unavailable'):
                RAGEngine(Path(self.tmp.name) / 'chroma', state_engine=self.db)
        chroma.assert_not_called()
        self.assertEqual(self.rag.vectors.document(document['document_id'])['state'], 'CURRENT')

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

    def test_invalid_embedding_batch_is_not_checkpointed_or_searchable(self):
        for bad in ([], [float('nan'), 1], [float('inf'), 1], [1e100, 1], [True, 1]):
            with self.subTest(vector=bad), patch.object(self.embed, 'embed',
                side_effect=lambda texts: [bad for _ in texts]):
                with self.assertRaises(ValueError):
                    self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
            with self.db.connect() as db:
                self.assertEqual(db.execute(text('SELECT COUNT(*) FROM scoped_vector_blobs')).scalar(), 0)
                self.assertEqual(db.execute(text('SELECT COUNT(*) FROM scoped_chunks')).scalar(), 0)
        self.assertEqual(self.rag.count, 0)
        # A subsequent valid batch still completes the same seal.
        self.assertGreater(self.rag.scoped.seal(self.learner, self.video, self.cues, 12)['sealed_added'], 0)

    def test_mixed_embedding_dimensions_roll_back_the_batch(self):
        with patch.object(self.embed, 'embed',
                          side_effect=lambda texts: [[1.0] * (i + 2) for i, _ in enumerate(texts)]):
            with self.assertRaisesRegex(ValueError, 'inconsistent vector dimensions'):
                self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        with self.db.connect() as db:
            self.assertEqual(db.execute(text('SELECT COUNT(*) FROM scoped_vector_blobs')).scalar(), 0)
            self.assertEqual(db.execute(text('SELECT COUNT(*) FROM scoped_chunks')).scalar(), 0)

    def test_overlapping_cues_require_the_entire_caption_span(self):
        cues = [{'start': 0, 'end': 10, 'text': 'The long caption contains material through ten seconds.'},
                {'start': 1, 'end': 2, 'text': 'A separate short caption overlaps the long caption.'}]
        self.rag.scoped.seal(self.learner, self.video, cues, 10)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 2, 'wall_ms': 2000, 'rate': 1}])
        self.assertEqual(self.rag.scoped.retrieve(self.learner, self.video, 'caption'), [])

    def test_caption_revision_can_reuse_an_interval_sequence(self):
        self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 12, 'wall_ms': 12000, 'rate': 1}])
        changed = [{**cue, 'text': cue['text'] + ' revised'} for cue in self.cues]
        self.rag.scoped.seal(self.learner, self.video, changed, 12)
        result = self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 12, 'wall_ms': 12000, 'rate': 1}])
        self.assertGreater(result['promoted'], 0)

    def test_old_revision_intervals_cannot_unlock_replacement_captions(self):
        original = self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        changed = [{**cue, 'text': cue['text'] + ' revised'} for cue in self.cues]
        replacement = self.rag.scoped.seal(self.learner, self.video, changed, 12)
        intervals = [{'start': 0, 'end': 12, 'wall_ms': 12000, 'rate': 1}]
        with self.assertRaisesRegex(ValueError, 'revision changed'):
            self.rag.scoped.intervals(self.learner, self.video, 1, intervals,
                                      revision=original['revision'])
        self.assertEqual(self.rag.scoped.retrieve(self.learner, self.video, 'lesson'), [])
        self.assertGreater(self.rag.scoped.intervals(self.learner, self.video, 1, intervals,
                           revision=replacement['revision'])['promoted'], 0)

    def test_transfer_requires_observation_of_matching_source_cues(self):
        text_a = ' '.join(f'opening{i}' for i in range(50))
        text_b = ' '.join(f'ending{i}' for i in range(50))
        source = [{'start': 0, 'end': 10, 'text': text_a},
                  {'start': 10, 'end': 12, 'text': text_b}]
        target = [{'start': 0, 'end': 1, 'text': text_a},
                  {'start': 1, 'end': 3, 'text': text_b}]
        self.rag.scoped.seal(self.learner, self.video, source, 12)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 4, 'wall_ms': 4000, 'rate': 1}])
        self.rag.scoped.seal(self.learner, 'youtube:uneven', target, 3)
        self.assertEqual(self.rag.scoped.retrieve(self.learner, 'youtube:uneven', 'opening'), [])
        self.rag.scoped.intervals(self.learner, self.video, 2,
            [{'start': 4, 'end': 10, 'wall_ms': 6000, 'rate': 1}])
        found = self.rag.scoped.retrieve(self.learner, 'youtube:uneven', 'opening')
        self.assertTrue(found)
        self.assertTrue(all('ending0' not in item['snippet'] for item in found))

    def test_source_revision_revokes_transferred_evidence(self):
        self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 12, 'wall_ms': 12000, 'rate': 1}])
        self.rag.scoped.seal(self.learner, 'youtube:copy', self.cues, 12)
        self.assertTrue(self.rag.scoped.retrieve(self.learner, 'youtube:copy', 'lesson'))
        changed = [{**cue, 'text': f'Replacement unrelated botany caption {i}.'}
                   for i, cue in enumerate(self.cues)]
        self.rag.scoped.seal(self.learner, self.video, changed, 12)
        self.assertEqual(self.rag.scoped.retrieve(self.learner, 'youtube:copy', 'lesson'), [])

    def test_changed_embedding_model_does_not_reuse_old_scoped_vectors(self):
        self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 12, 'wall_ms': 12000, 'rate': 1}])
        other_embed = FakeEmbed()
        other_embed.model = 'different-scoped-test'
        upgraded = RAGEngine(Path(self.tmp.name) / 'chroma', state_engine=self.db,
                             embeddings=other_embed)
        self.assertEqual(upgraded.count, 0)
        self.assertEqual(upgraded.scoped.retrieve(self.learner, self.video, 'lesson'), [])
        upgraded.scoped.seal(self.learner, self.video, self.cues, 12)
        self.assertGreater(other_embed.calls, 0)
        self.assertTrue(upgraded.scoped.retrieve(self.learner, self.video, 'lesson'))

    def test_scoped_leases_survive_restart_and_restore_after_last_close(self):
        self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 12, 'wall_ms': 12000, 'rate': 1}])
        chunks = self.rag.scoped.retrieve(self.learner, self.video, 'lesson')
        questions = [{'citations': [chunks[0]['chunk_id']]}]
        self.rag.leases.open_scoped('restart-a', self.learner, self.video, questions)
        self.rag.leases.open_scoped('restart-b', self.learner, self.video, questions)
        restarted = RAGEngine(Path(self.tmp.name) / 'chroma', state_engine=self.db,
                             embeddings=self.embed)
        self.assertEqual(restarted.scoped.retrieve(self.learner, self.video, 'lesson'), [])
        restarted.leases.close('restart-a')
        self.assertEqual(restarted.scoped.retrieve(self.learner, self.video, 'lesson'), [])
        restarted.leases.close('restart-b')
        self.assertEqual(restarted.scoped.retrieve(self.learner, self.video, 'lesson'), chunks)
        with self.db.connect() as db:
            self.assertEqual(db.execute(text('SELECT MAX(demote_refcount) FROM scoped_chunks')).scalar(), 0)

    def test_leases_hide_counterparts_with_uneven_caption_timing(self):
        source = [{'start': 0, 'end': 10, 'text': ' '.join(f'opening{i}' for i in range(50))},
                  {'start': 10, 'end': 12, 'text': ' '.join(f'ending{i}' for i in range(50))}]
        target = [{**source[0], 'start': 0, 'end': 1},
                  {**source[1], 'start': 1, 'end': 3}]
        with patch.dict('os.environ', {'E_MACRO_WORDS': '50'}):
            self.rag.scoped.macro_words = 50
            self.rag.scoped.seal(self.learner, self.video, source, 12)
            self.rag.scoped.intervals(self.learner, self.video, 1,
                [{'start': 0, 'end': 12, 'wall_ms': 12000, 'rate': 1}])
            self.rag.scoped.seal(self.learner, 'youtube:uneven-copy', target, 3)
        with self.db.connect() as db:
            citation = db.execute(text("""SELECT chroma_id FROM scoped_chunks
                WHERE video_key=:video AND t_start=10000 AND granularity='micro'"""),
                {'video': self.video}).scalar_one()
        with patch.object(self.rag.leases, 'near_cos', 1.1):
            self.rag.leases.open_scoped('uneven-lease', self.learner, self.video,
                                       [{'citations': [citation]}])
        found = self.rag.scoped.retrieve(self.learner, 'youtube:uneven-copy', 'ending')
        self.assertTrue(found)
        self.assertTrue(all('ending0' not in item['snippet'] for item in found))

    def test_transfer_does_not_chain_or_cross_learners(self):
        self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 12, 'wall_ms': 12000, 'rate': 1}])
        self.rag.scoped.seal(self.learner, 'youtube:second', self.cues, 12)
        self.assertTrue(self.rag.scoped.retrieve(self.learner, 'youtube:second', 'lesson'))
        self.rag.scoped.seal('another-learner', 'youtube:third', self.cues, 12)
        self.assertEqual(self.rag.scoped.retrieve('another-learner', 'youtube:third', 'lesson'), [])
        # Exercise the transfer path using only a indirectly observed source.
        self.rag.scoped.seal(self.learner, 'youtube:third', self.cues, 12)
        with self.db.begin() as db:
            db.execute(text("""UPDATE scoped_chunks SET state='SEALED',source_video_key=NULL
                WHERE video_key='youtube:third'"""))
        self.rag.scoped.transfer._transfer(self.learner, 'youtube:second', 'youtube:third')
        self.assertEqual(self.rag.scoped.retrieve(self.learner, 'youtube:third', 'lesson'), [])

    def test_source_revision_preserves_independently_observed_target(self):
        self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 12, 'wall_ms': 12000, 'rate': 1}])
        self.rag.scoped.seal(self.learner, 'youtube:independent', self.cues, 12)
        self.rag.scoped.intervals(self.learner, 'youtube:independent', 1,
            [{'start': 0, 'end': 12, 'wall_ms': 12000, 'rate': 1}])
        changed = [{**cue, 'text': f'Distinct botany replacement caption {i}.'}
                   for i, cue in enumerate(self.cues)]
        self.rag.scoped.seal(self.learner, self.video, changed, 12)
        self.assertTrue(self.rag.scoped.retrieve(self.learner, 'youtube:independent', 'lesson'))

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

    def test_answer_cache_distinguishes_question_case(self):
        self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 12, 'wall_ms': 12000, 'rate': 1}])
        with patch.object(routes, 'rag_engine', self.rag), patch.object(
            routes.llm_service, 'answer_with_rag',
            side_effect=lambda question, *_args, **_kwargs: f'Answer for {question}') as answer:
            first = routes.ask_lesson(AskRequest(question='What is US?', source_type='video',
                learner_key=self.learner, video_key=self.video))
            second = routes.ask_lesson(AskRequest(question='What is us?', source_type='video',
                learner_key=self.learner, video_key=self.video))
            self.assertNotEqual(first['answer'], second['answer'])
            self.assertEqual(answer.call_count, 2)
            self.assertEqual(routes.ask_lesson(AskRequest(question='What is US?', source_type='video',
                learner_key=self.learner, video_key=self.video)), first)
            self.assertEqual(answer.call_count, 2)

    def test_answer_cache_preserves_whitespace_in_quoted_questions(self):
        cache = self.rag.answer_cache
        arguments = ('scoped:learner-1|youtube:test123', 'model', 5, None)
        self.assertNotEqual(cache.key('Explain "a  b"', *arguments),
                            cache.key('Explain "a b"', *arguments))

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
            video_key=self.video, batch_seq=1, revision='a' * 64,
            intervals=[{'start': 0, 'end': 5, 'wall_ms': 5000, 'rate': 1}])
        contexts = []
        def answer(_question, chunks, *_args, **_kwargs):
            contexts.extend(chunks)
            return 'An answer from observed material.'
        with patch.object(vector_routes, 'rag_engine', self.rag), \
             patch.object(routes, 'rag_engine', self.rag), \
             patch.object(routes.llm_service, 'answer_with_rag', side_effect=answer):
            observed.revision = vector_routes.seal_scoped(seal)['revision']
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
