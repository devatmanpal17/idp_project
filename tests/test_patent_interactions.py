"""Cross-feature regressions using real temporary SQL/Chroma and controlled interleavings."""
import hashlib
import json
import tempfile
import unittest
import random
from threading import Event, Thread
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, text

from backend.models import AskRequest, SummarizeRequest, GenerateQuizRequest
from backend.routes import rag as routes
from backend.routes import jobs
from ml.rag_engine import RAGEngine
from ml.temporal import Caption, Interval, temporal_chunks
from ml.llm_service import LLMService
from ml.analytics import QuizAnalyticsStore


class DeterministicEmbeddings:
    model = 'interaction-test'

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return [[(value - 127.5) / 127.5 for value in hashlib.sha256(item.encode()).digest()]
                for item in texts]


class PatentInteractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.db = create_engine(f'sqlite:///{(self.root / "state.db").as_posix()}')
        self.embed = DeterministicEmbeddings()
        self.rag = RAGEngine(self.root / 'chroma', state_engine=self.db, embeddings=self.embed)
        self.learner, self.video = 'interaction-learner', 'youtube:interaction'
        self.cues = [{'start': float(i), 'end': float(i + 1),
                      'text': f'Lesson section {i} explains a distinct copper circuit procedure.'}
                     for i in range(12)]

    def tearDown(self):
        self.db.dispose()
        self.temp.cleanup()

    def observed(self):
        result = self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        self.rag.scoped.intervals(self.learner, self.video, result['last_batch_seq'] + 1,
            [{'start': 0, 'end': 12, 'wall_ms': 12000, 'rate': 1}], revision=result['revision'])
        return self.rag.scoped.retrieve(self.learner, self.video, 'copper circuit')

    def lease(self, chunks):
        self.rag.leases.open_scoped('interleaved-quiz', self.learner, self.video,
                                    [{'citations': [chunks[0]['chunk_id']]}])

    def test_transfer_does_not_erase_semantically_significant_punctuation(self):
        prefix = ' '.join(f'context{i}' for i in range(30))
        for index, (original, changed) in enumerate([
            ('x > 5', 'x < 5'), ('x != 5', 'x == 5'),
            ('left-right', 'leftright'), ('-5', '5'), ('a_b', 'ab'),
        ]):
            with self.subTest(original=original, changed=changed):
                source = [{'start': 0, 'end': 2, 'text': f'{prefix} the code expression is {original}'}]
                target = [{**source[0], 'text': f'{prefix} the code expression is {changed}'}]
                seal = self.rag.scoped.seal(self.learner, self.video, source, 2)
                self.rag.scoped.intervals(self.learner, self.video, 1,
                    [{'start': 0, 'end': 2, 'wall_ms': 2000, 'rate': 1}], revision=seal['revision'])
                copy = f'youtube:operator-copy-{index}'
                self.rag.scoped.seal(self.learner, copy, target, 2)
                self.assertEqual(self.rag.scoped.retrieve(self.learner, copy, 'expression'), [])

    def test_rolling_captions_preserve_case_and_operator_changes(self):
        for original, changed in [('A', 'a'), ('x > 5', 'x < 5'),
                                  ('x != 5', 'x == 5'), ('-5', '5')]:
            with self.subTest(original=original, changed=changed):
                chunks, _ = temporal_chunks([
                    Caption(start_ms=0, end_ms=1000, text=f'The expression is {original}'),
                    Caption(start_ms=500, end_ms=1500, text=f'The expression is {changed}')])
                self.assertEqual(len(chunks), 2)
                self.assertIn(changed, chunks[-1]['text'])

    def test_answer_cannot_publish_or_cache_evidence_leased_during_generation(self):
        chunks = self.observed()
        def interleave(_question, context, *_args, **_kwargs):
            self.lease(context)
            return f"The secret explanation [{context[0]['chunk_id']}]"
        with patch.object(routes, 'rag_engine', self.rag), \
             patch.object(routes.llm_service, 'answer_with_rag', side_effect=interleave), \
             self.assertRaises(HTTPException) as caught:
            routes.ask_lesson(AskRequest(question='Explain copper circuit', source_type='video',
                learner_key=self.learner, video_key=self.video))
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(self.rag.answer_cache.status()['entries'], 0)
        self.assertEqual(self.rag.scoped.retrieve(self.learner, self.video, 'copper circuit'), [])

    def test_summary_cannot_publish_evidence_leased_during_generation(self):
        self.observed()
        def interleave(_topic, context):
            self.lease(context)
            return 'The old, now leased evidence summary.'
        with patch.object(routes, 'rag_engine', self.rag), \
             patch.object(routes.llm_service, 'summarize_with_rag', side_effect=interleave), \
             self.assertRaises(HTTPException) as caught:
            routes.summarize_page(SummarizeRequest(topic='Copper circuit', source_type='video',
                learner_key=self.learner, video_key=self.video))
        self.assertEqual(caught.exception.status_code, 422)

    def test_answer_cannot_publish_evidence_from_replaced_captions(self):
        self.observed()
        def interleave(_question, context, *_args, **_kwargs):
            self.rag.scoped.seal(self.learner, self.video,
                [{**cue, 'text': f'Replacement botany section {i} about leaf tissue.'}
                 for i, cue in enumerate(self.cues)], 12)
            return f"The outdated circuit explanation [{context[0]['chunk_id']}]"
        with patch.object(routes, 'rag_engine', self.rag), \
             patch.object(routes.llm_service, 'answer_with_rag', side_effect=interleave), \
             self.assertRaises(HTTPException) as caught:
            routes.ask_lesson(AskRequest(question='Explain copper circuit', source_type='video',
                learner_key=self.learner, video_key=self.video))
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(self.rag.answer_cache.status()['entries'], 0)

    def test_failed_index_delete_cannot_leave_cached_lease_evidence_retrievable(self):
        doc = self.rag.vectors.register('https://example.test/lease', 'Lease lesson', [
            Caption(start_ms=0, end_ms=1000,
                    text='The protected copper lantern caption is the quiz evidence.')])['document_id']
        for chunk in self.rag.vectors.pending(doc):
            self.rag.vectors.embed_chunk(doc, chunk['id'])
        self.rag.vectors.observe(doc, 'lease-test-session', 1,
                                 [Interval(start_ms=0, end_ms=1000)], 'rendered-frame')
        chunks = self.rag.retrieve('copper lantern', document_id=doc)
        self.assertTrue(chunks)
        with patch.object(self.rag.collection, 'delete', side_effect=OSError('index unavailable')):
            with self.assertRaises(OSError):
                self.rag.leases.open('failed-delete-quiz', doc,
                                     [{'citations': [chunks[0]['chunk_id']]}])
        self.assertEqual(self.rag.retrieve('copper lantern', document_id=doc), [])
        self.assertEqual(self.rag.retrieve('copper lantern'), [])

    def test_model_switch_during_generation_cannot_poison_another_models_cache(self):
        self.observed()
        service = LLMService()
        original = service.model
        def interleave(*_args, **_kwargs):
            service.configure('ollama', model='other-model')
            service.configure('ollama', model=original)
            return 'An answer generated while model configuration changed.'
        service.answer_with_rag = interleave
        with patch.object(routes, 'rag_engine', self.rag), patch.object(routes, 'llm_service', service), \
             self.assertRaises(HTTPException) as caught:
            routes.ask_lesson(AskRequest(question='Explain copper circuit', source_type='video',
                learner_key=self.learner, video_key=self.video))
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(self.rag.answer_cache.status()['entries'], 0)

    def test_old_transfer_policy_is_rechecked_on_restart_without_embedding(self):
        prefix = ' '.join(f'context{i}' for i in range(30))
        source = [{'start': 0, 'end': 2, 'text': f'{prefix} the comparison is x > 5'}]
        target = [{**source[0], 'text': f'{prefix} the comparison is x < 5'}]
        seal = self.rag.scoped.seal(self.learner, self.video, source, 2)
        self.rag.scoped.intervals(self.learner, self.video, 1,
            [{'start': 0, 'end': 2, 'wall_ms': 2000, 'rate': 1}], revision=seal['revision'])
        copy = 'youtube:legacy-operator-copy'
        self.rag.scoped.seal(self.learner, copy, target, 2)
        # Simulate persisted rows activated by the previous punctuation-erasing policy.
        with self.db.begin() as db:
            db.execute(text("""UPDATE scoped_chunks SET state='ACTIVE',provenance='transferred',
                source_video_key=:source WHERE video_key=:copy"""), {'source': self.video, 'copy': copy})
        before = self.embed.calls
        restarted = RAGEngine(self.root / 'chroma', state_engine=self.db, embeddings=self.embed)
        self.assertEqual(restarted.scoped.retrieve(self.learner, copy, 'comparison'), [])
        self.assertEqual(self.embed.calls, before)

    def test_recovery_after_failed_restore_clears_empty_retrieval_cache(self):
        doc = self.rag.vectors.register('https://example.test/restore', 'Restore', [
            Caption(start_ms=0, end_ms=1000, text='Restore this protected circuit evidence.')])['document_id']
        for chunk in self.rag.vectors.pending(doc):
            self.rag.vectors.embed_chunk(doc, chunk['id'])
        self.rag.vectors.observe(doc, 'restore-test-session', 1,
            [Interval(start_ms=0, end_ms=1000)], 'rendered-frame')
        chunks = self.rag.retrieve('circuit', document_id=doc)
        self.rag.leases.open('restore-fault-quiz', doc, [{'citations': [chunks[0]['chunk_id']]}])
        self.assertEqual(self.rag.retrieve('circuit', document_id=doc), [])
        with patch.object(self.rag.collection, 'upsert', side_effect=OSError('restore interrupted')):
            with self.assertRaises(OSError):
                self.rag.leases.close('restore-fault-quiz')
        self.assertEqual(self.rag.retrieve('circuit', document_id=doc), [])
        self.rag.leases.recover()
        self.assertTrue(self.rag.retrieve('circuit', document_id=doc))

    def test_valid_old_policy_transfer_recovers_after_an_index_fault_without_embedding(self):
        self.observed()
        copy = 'youtube:valid-legacy-copy'
        self.rag.scoped.seal(self.learner, copy, self.cues, 12)
        with self.db.begin() as db:
            db.execute(text('DELETE FROM scoped_transfer_policy'))
        before = self.embed.calls
        with patch.object(self.rag.collection, 'delete', side_effect=OSError('policy index fault')):
            with self.assertRaises(OSError):
                self.rag.scoped.transfer.recover()
        with self.db.connect() as db:
            self.assertGreater(db.execute(text('SELECT COUNT(*) FROM scoped_transfer_rechecks')).scalar(), 0)
        self.assertEqual(self.rag.scoped.retrieve(self.learner, copy, 'circuit'), [])
        self.rag.scoped.transfer.recover()
        self.assertEqual(self.embed.calls, before)
        self.assertTrue(self.rag.scoped.retrieve(self.learner, copy, 'circuit'))
        with self.db.connect() as db:
            self.assertEqual(db.execute(text('SELECT COUNT(*) FROM scoped_transfer_rechecks')).scalar(), 0)

    def test_quiz_publication_rejects_concurrent_lease_or_source_revision(self):
        for mutation in ('lease', 'revision'):
            with self.subTest(mutation=mutation):
                chunks = self.observed()
                def interleave(**kwargs):
                    context = kwargs['context_chunks']
                    if mutation == 'lease':
                        self.lease(context)
                    else:
                        self.rag.scoped.seal(self.learner, self.video,
                            [{**cue, 'text': f'Replacement botanical tissue section {i}.'}
                             for i, cue in enumerate(self.cues)], 12)
                    return [{'citations': [context[0]['chunk_id']]}]
                with patch.object(routes, 'rag_engine', self.rag), \
                     patch.object(routes.llm_service, 'generate_quiz_with_rag', side_effect=interleave), \
                     patch.object(routes.quiz_analytics, 'save_quiz') as save, \
                     self.assertRaises(HTTPException) as caught:
                    routes.generate_quiz(GenerateQuizRequest(topic='Copper circuit', question_count=3,
                        source_type='video', learner_key=self.learner, video_key=self.video))
                self.assertEqual(caught.exception.status_code, 422)
                save.assert_not_called()
                self.rag.leases.close('interleaved-quiz')

    def test_lease_can_open_on_another_thread_while_model_runs(self):
        chunks = self.observed()
        entered, release = Event(), Event()
        result = []
        def model(*_args, **_kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('The model wait was not released')
            return 'A now-protected circuit answer.'
        def request():
            try:
                result.append(routes.ask_lesson(AskRequest(question='Explain copper circuit',
                    source_type='video', learner_key=self.learner, video_key=self.video)))
            except HTTPException as exc:
                result.append(exc.status_code)
        with patch.object(routes, 'rag_engine', self.rag), \
             patch.object(routes.llm_service, 'answer_with_rag', side_effect=model):
            worker = Thread(target=request)
            worker.start()
            try:
                self.assertTrue(entered.wait(3))
                self.lease(chunks)
            finally:
                release.set()
                worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result, [422])

    def test_seeded_observation_and_overlapping_leases_keep_sql_and_index_in_sync(self):
        seal = self.rag.scoped.seal(self.learner, self.video, self.cues, 12)
        rng = random.Random(917)
        sequence, leases = 0, []
        for step in range(100):
            action = rng.randrange(4)
            if action <= 1:
                start = rng.randrange(12)
                sequence += 1
                self.rag.scoped.intervals(self.learner, self.video, sequence,
                    [{'start': start, 'end': start + 1, 'wall_ms': 1000, 'rate': 1}], revision=seal['revision'])
            elif action == 2:
                with self.db.connect() as db:
                    active = db.execute(text("SELECT chroma_id FROM scoped_chunks WHERE state IN ('ACTIVE','DEMOTED')")).scalars().all()
                if active:
                    quiz = f'seeded-quiz-{step}'
                    self.rag.leases.open_scoped(quiz, self.learner, self.video,
                                               [{'citations': [rng.choice(active)]}])
                    leases.append(quiz)
            elif leases:
                self.rag.leases.close(leases.pop(rng.randrange(len(leases))))
            with self.db.connect() as db:
                rows = db.execute(text('SELECT chroma_id,state,demote_refcount FROM scoped_chunks')).all()
            expected = {key for key, state, count in rows if state == 'ACTIVE' and count == 0}
            self.assertEqual(set(self.rag.collection.get(include=[])['ids']), expected)
            self.assertTrue(all(count >= 0 and (count == 0 or state != 'ACTIVE') for _, state, count in rows))
        for quiz in leases:
            self.rag.leases.close(quiz)
        with self.db.connect() as db:
            self.assertEqual(db.execute(text('SELECT MAX(demote_refcount) FROM scoped_chunks')).scalar(), 0)

    def test_durable_output_and_cached_output_are_locked_without_exposing_private_proofs(self):
        chunks = self.observed()
        payload = AskRequest(question='Explain copper circuit', source_type='video',
            learner_key=self.learner, video_key=self.video).model_dump()
        with patch.object(routes, 'rag_engine', self.rag), patch.object(jobs, 'rag_engine', self.rag), \
             patch.object(jobs, 'store', self.rag.jobs), \
             patch.object(routes.llm_service, 'answer_with_rag', return_value='An uncited circuit answer.') as model:
            ids = []
            for _ in range(2):
                job, _ = self.rag.jobs.create('ask', payload)
                jobs.run_job(job)
                public = jobs.job_status(job)
                self.assertEqual(public['status'], 'succeeded')
                self.assertEqual(public['checkpoint'], {'output_validated': True})
                self.assertNotIn('evidence', public)
                ids.append(job)
            self.assertEqual(model.call_count, 1)  # The second job hits the answer cache.
            self.lease(chunks)
            for job in ids:
                with self.assertRaises(HTTPException) as caught:
                    jobs.job_status(job)
                self.assertEqual(caught.exception.status_code, 409)
            self.rag.leases.close('interleaved-quiz')
            self.assertEqual(jobs.job_status(ids[0])['result']['answer'], 'An uncited circuit answer.')
            self.assertEqual(model.call_count, 1)

    def test_durable_quiz_can_deliver_under_its_own_lease_but_not_another_quiz_lease(self):
        self.observed()
        analytics = QuizAnalyticsStore(engine=self.db)
        payload = GenerateQuizRequest(topic='Copper circuit', question_count=3,
            source_type='video', learner_key=self.learner, video_key=self.video).model_dump()
        def model(**kwargs):
            chunk = kwargs['context_chunks'][0]
            return [{'q': 'What material does the lesson discuss?',
                     'choices': ['Copper', 'Silver', 'Gold', 'Iron'], 'answer': 'Copper',
                     'why': 'The lesson describes a copper circuit procedure.',
                     'citations': [chunk['chunk_id']], 'bloom_level': 'Remember',
                     'evidence_quote': chunk['snippet']}]
        with patch.object(routes, 'rag_engine', self.rag), patch.object(jobs, 'rag_engine', self.rag), \
             patch.object(jobs, 'store', self.rag.jobs), patch.object(routes, 'quiz_analytics', analytics), \
             patch.object(routes.llm_service, 'generate_quiz_with_rag', side_effect=model):
            job, _ = self.rag.jobs.create('quiz', payload)
            jobs.run_job(job)
            public = jobs.job_status(job)
            self.assertEqual(public['status'], 'succeeded', public)
            quiz = public['result']
            self.assertNotIn('answer', quiz['questions'][0])
            with self.db.connect() as db:
                self.assertEqual(db.execute(text("SELECT COUNT(*) FROM evidence_leases WHERE state='OPEN'")).scalar(), 1)
            self.rag.leases.open_scoped('other-quiz', self.learner, self.video, quiz['questions'])
            with self.assertRaises(HTTPException) as caught:
                jobs.job_status(job)
            self.assertEqual(caught.exception.status_code, 409)
            self.rag.leases.close('other-quiz')
            self.assertEqual(jobs.job_status(job)['result']['quiz_id'], quiz['quiz_id'])
            # Resume the already validated owning quiz without repeating model work.
            private = self.rag.jobs.get(job, private=True)
            resumed, _ = self.rag.jobs.create('quiz', payload)
            self.rag.jobs.claim(resumed)
            self.rag.jobs.checkpoint(resumed, 'VALIDATING', private['checkpoint'])
            self.rag.jobs.recover()
            with patch.dict(jobs.HANDLERS, quiz=lambda req: self.fail('Must resume the checkpoint')):
                jobs.run_job(resumed)
            self.assertEqual(jobs.job_status(resumed)['status'], 'succeeded')
            self.rag.leases.close(quiz['quiz_id'])
            self.assertEqual(jobs.job_status(job)['status'], 'succeeded')

    def test_restart_cannot_replay_validated_output_after_evidence_is_leased(self):
        chunks = self.observed()
        payload = AskRequest(question='Explain copper circuit', source_type='video',
            learner_key=self.learner, video_key=self.video).model_dump()
        job, _ = self.rag.jobs.create('ask', payload)
        with patch.object(routes, 'rag_engine', self.rag), patch.object(jobs, 'rag_engine', self.rag), \
             patch.object(jobs, 'store', self.rag.jobs), \
             patch.object(routes.llm_service, 'answer_with_rag', return_value='An uncited circuit answer.'), \
             patch.object(self.rag.jobs, 'finish', side_effect=SystemExit('simulated process crash')):
            with self.assertRaises(SystemExit):
                jobs.run_job(job)
        self.assertEqual(self.rag.jobs.get(job)['stage'], 'VALIDATING')
        self.lease(chunks)
        restarted = RAGEngine(self.root / 'chroma', state_engine=self.db, embeddings=self.embed)
        restarted.jobs.recover()
        with patch.object(jobs, 'rag_engine', restarted), patch.object(jobs, 'store', restarted.jobs), \
             patch.dict(jobs.HANDLERS, ask=lambda req: self.fail('Must not regenerate checkpointed output')):
            jobs.run_job(job)
        result = restarted.jobs.get(job)
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn('result', result)

    def test_completed_job_cannot_return_answer_after_caption_revision_changes(self):
        self.observed()
        payload = AskRequest(question='Explain copper circuit', source_type='video',
            learner_key=self.learner, video_key=self.video).model_dump()
        with patch.object(routes, 'rag_engine', self.rag), patch.object(jobs, 'rag_engine', self.rag), \
             patch.object(jobs, 'store', self.rag.jobs), \
             patch.object(routes.llm_service, 'answer_with_rag', return_value='The old circuit answer.'):
            job, _ = self.rag.jobs.create('ask', payload)
            jobs.run_job(job)
            self.rag.scoped.seal(self.learner, self.video,
                [{**cue, 'text': f'Replacement botanical tissue section {i}.'}
                 for i, cue in enumerate(self.cues)], 12)
            with self.assertRaises(HTTPException) as caught:
                jobs.job_status(job)
            self.assertEqual(caught.exception.status_code, 409)


if __name__ == '__main__':
    unittest.main()
