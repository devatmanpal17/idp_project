import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from sqlalchemy import create_engine
from ml.persistent_jobs import JobStore
from ml.scheduler import ResourceController
from backend.routes import jobs
from backend.routes import vectors


class JobsSchedulerTests(unittest.TestCase):
    def test_restart_checkpoint_and_idempotency(self):
        with tempfile.TemporaryDirectory() as folder:
            engine = create_engine(f'sqlite:///{Path(folder).as_posix()}/jobs.db')
            first = JobStore(engine)
            job, created = first.create('speculate', {'document_id': 'd'}, 'request-001')
            self.assertTrue(created)
            self.assertTrue(first.claim(job))
            self.assertFalse(first.claim(job))
            first.checkpoint(job, 'SEALED', {'last_completed_chunk': 'chunk-1'})
            second = JobStore(engine)
            self.assertEqual(second.recover(), [job])
            self.assertEqual(second.get(job)['checkpoint'], {'last_completed_chunk': 'chunk-1'})
            self.assertEqual(second.get(job)['resume_count'], 1)
            self.assertFalse(second.create('speculate', {'document_id': 'd'}, 'request-001')[1])
            second.claim(job); second.finish(job, {'safe': True})
            self.assertEqual(second.get(job)['result'], {'safe': True})
            self.assertEqual(second.recover(), [])
            second.cancel_documents(['d'])
            self.assertNotIn('result', second.get(job))
            engine.dispose()

    def test_admission_budget_memory_and_interactive_work(self):
        c = ResourceController(ram_budget=1000000)
        self.assertEqual(c.decide(budget_ms=1000, idle=True)['batch_size'], 1)
        c.measured(200)
        self.assertEqual(c.decide(budget_ms=1000, idle=True)['batch_size'], 5)
        with c.interactive_work():
            self.assertEqual(c.decide(budget_ms=1000, idle=True)['batch_size'], 0)
        for kwargs in [dict(idle=False), dict(idle=True, queue_depth=3), dict(idle=True, occupancy=1000000)]:
            self.assertEqual(c.decide(budget_ms=1000, **kwargs)['batch_size'], 0)
        cold = ResourceController(ram_budget=32768)
        self.assertEqual(cold.decide(budget_ms=1000, idle=True, occupancy=1)['batch_size'], 0)
        self.assertEqual(cold.decide(budget_ms=0, idle=True)['batch_size'], 0)

    def test_observed_only_admission_after_rewind_excludes_future_chunks(self):
        rag = Mock()
        rag.vectors.pending.return_value = [
            {'id': 'future', 'start_ms': 100000, 'end_ms': 101000},
            {'id': 'watched', 'start_ms': 800000, 'end_ms': 801000},
        ]
        rag.vectors.intervals.return_value = [[800000, 801000]]
        rag.hot_cache = None
        with patch.object(vectors, 'rag_engine', rag), patch.object(
            jobs.store, 'queue_depth', return_value=0
        ), patch.object(jobs, 'submit', return_value={'job_id': 'test'}) as submit, patch(
            'ml.scheduler.controller', ResourceController()
        ):
            vectors.speculate(vectors.SpeculationRequest(
                document_id='doc', position_ms=0, idle=True, observed_only=True))
        self.assertEqual(submit.call_args.args[1]['chunk_ids'], ['watched'])

    def test_slow_cold_load_does_not_permanently_starve_speculation(self):
        now = [0]
        controller = ResourceController(clock=lambda: now[0])
        controller.decide(budget_ms=2000, idle=True)
        controller.measured(12000)
        self.assertEqual(controller.decide(budget_ms=2000, idle=True)['batch_size'], 0)
        now[0] = 31
        self.assertEqual(controller.decide(budget_ms=2000, idle=True)['reason'], 'cost_recovery_probe')
        self.assertEqual(controller.decide(budget_ms=2000, idle=True)['batch_size'], 0)


class JobWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f'sqlite:///{Path(self.tmp.name).as_posix()}/jobs.db')
        self.store = JobStore(self.engine)
        self.patch = patch.object(jobs, 'store', self.store)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.engine.dispose()
        self.tmp.cleanup()

    def test_restart_after_validated_output_does_not_regenerate(self):
        job, _ = self.store.create('ask', {'question': 'Explain gravity'})
        result = {'answer': 'A persisted answer', 'sources': []}
        with patch.dict(jobs.HANDLERS, ask=lambda req: result), patch.object(
            self.store, 'finish', side_effect=KeyboardInterrupt('simulated process loss')
        ):
            with self.assertRaises(KeyboardInterrupt):
                jobs.run_job(job)
        self.assertEqual(self.store.get(job)['stage'], 'VALIDATING')
        self.assertNotIn('result', self.store.get(job)['checkpoint'])
        self.store.recover()
        with patch.dict(jobs.HANDLERS, ask=lambda req: self.fail('must reuse validated output')):
            jobs.run_job(job)
        self.assertEqual(self.store.get(job)['result'], result)

    def test_seal_job_accepts_full_cues_and_returns_sequence_checkpoint(self):
        payload = {'learner_key': 'learner', 'video_key': 'youtube:example',
                   'duration': 3, 'cues': [{'start': 0, 'end': 1, 'text': 'One cue.'}]}
        with patch.object(jobs._executor, 'submit'):
            created = jobs.create_job(jobs.AIJobRequest(
                request_id='request-seal-001', operation='seal', payload=payload))
        result = {'sealed_added': 1, 'last_batch_seq': 9}
        with patch.dict(jobs.HANDLERS, seal=lambda req: result):
            jobs.run_job(created['job_id'])
        self.assertEqual(self.store.get(created['job_id'])['result'], result)

    def test_cancelled_document_cannot_publish_late_result_or_resume(self):
        job, _ = self.store.create('ask', {'document_id': 'deleted', 'question': 'private content'})
        self.store.claim(job)
        self.store.checkpoint(job, 'VALIDATING', {'result': {'answer': 'private answer'}})
        self.store.cancel_documents(['deleted'])
        self.store.finish(job, result={'answer': 'late completion'})
        self.store.checkpoint(job, 'VALIDATING', {'result': 'late checkpoint'})
        self.assertEqual(self.store.get(job, private=True)['payload'], {})
        self.assertEqual(self.store.get(job)['checkpoint'], {})
        self.assertNotIn('result', self.store.get(job))
        self.assertEqual(self.store.recover(), [])

    def test_empty_exception_is_failed_and_duplicate_submission_runs_once(self):
        with patch.object(jobs._executor, 'submit') as submit:
            first = jobs.submit('ask', {'question': 'Explain gravity'}, 'request-123')
            self.assertEqual(jobs.submit('ask', {'question': 'Explain gravity'}, 'request-123'), first)
            with self.assertRaises(ValueError):
                jobs.submit('ask', {'question': 'Different question'}, 'request-123')
            self.assertEqual(submit.call_count, 1)
        def fail(req):
            raise RuntimeError()
        with patch.dict(jobs.HANDLERS, ask=fail):
            jobs.run_job(first['job_id'])
        self.assertEqual(self.store.get(first['job_id'])['status'], 'failed')
        self.assertTrue(self.store.get(first['job_id'])['error'])
