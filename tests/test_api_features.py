"""HTTP acceptance tests with real SQLite/Chroma and deterministic model responses."""
import copy
import json
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.exceptions import RequestValidationError
from backend.validation import request_validation_error
from sqlalchemy import create_engine
from backend.routes import rag, vectors, jobs, learning_data, settings, health, recommendations, runtime
from ml.analytics import QuizAnalyticsStore
from ml.rag_engine import RAGEngine
from ml.llm_service import LLMService
from test_quiz_guardrails import VALID
from test_vector_pipeline import CountingEmbeddings


LESSON = ('Binary search works on a sorted sequence and repeatedly cuts the search interval in half. '
          'At each step, the middle value is compared with the target. The comparison determines which '
          'half can be discarded. Sorting is required so that the remaining half still contains the target. '
          'This method reduces unnecessary comparisons during searching.')


class APIFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.db = create_engine(f'sqlite:///{(root / "state.db").as_posix()}')
        self.analytics = QuizAnalyticsStore(engine=self.db)
        embeddings = CountingEmbeddings()
        embeddings.health = lambda: {'online': True, 'embedding_model_ready': True, 'embedding_model': embeddings.model}
        self.rag = RAGEngine(root / 'chroma', state_engine=self.db, embeddings=embeddings)
        self.llm = LLMService()
        self.llm.status = lambda: {'online': True, 'model_ready': True, 'model': self.llm.model}
        def chat(system, prompt, schema=None, **kwargs):
            if schema:
                question = copy.deepcopy(VALID)
                import re
                citation = re.search(r'\[(C\d+|[a-f0-9]+_\d+)\]', prompt).group(1)
                question['questions'][0]['citations'] = [citation]
                return json.dumps(question)
            return 'Binary search repeatedly halves a sorted sequence.'
        self.llm._chat = chat
        self.stack = ExitStack()
        for module in [rag, vectors, jobs, learning_data, health]:
            self.stack.enter_context(patch.object(module, 'rag_engine', self.rag))
        for module in [rag, learning_data, health, recommendations]:
            self.stack.enter_context(patch.object(module, 'quiz_analytics', self.analytics))
        for module in [rag, settings, health]:
            self.stack.enter_context(patch.object(module, 'llm_service', self.llm))
        self.stack.enter_context(patch.object(jobs, 'store', self.rag.jobs))
        app = FastAPI()
        app.add_exception_handler(RequestValidationError, request_validation_error)
        for module in [rag, vectors, jobs, learning_data, settings, health, recommendations, runtime]:
            app.include_router(module.router)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.stack.close()
        self.db.dispose()
        self.tmp.cleanup()

    def post(self, path, payload, code=200):
        response = self.client.post('/api/' + path, json=payload)
        self.assertEqual(response.status_code, code, response.text)
        return response.json()

    def wait_job(self, job_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            response = self.client.get('/api/jobs/' + job_id)
            self.assertEqual(response.status_code, 200)
            job = response.json()
            if job['status'] in ('succeeded', 'failed'):
                self.assertEqual(job['status'], 'succeeded', job)
                return job
            time.sleep(.01)
        self.fail('Job did not finish in five seconds')

    def test_document_quiz_assessment_dashboard_history_and_settings(self):
        indexed = self.post('rag/ingest', {'title': 'Search lesson', 'topic': 'Search', 'content': LESSON})
        doc = indexed['document_id']
        retrieved = self.post('rag/retrieve', {'query': 'binary search', 'document_id': doc})
        self.assertEqual(len(retrieved['chunks']), 1)
        answer = self.post('rag/ask', {'question': 'How does binary search work?', 'document_id': doc})
        self.assertIn('sorted', answer['answer'])
        summary = self.post('rag/summarize', {'topic': 'Search', 'page_content': LESSON})
        self.assertIn('summary', summary)
        quiz = self.post('rag/generate-quiz', {'topic': 'Search', 'document_id': doc, 'question_count': 1})
        self.assertNotIn('answer', quiz['questions'][0])
        self.assertNotIn('evidence_quote', quiz['questions'][0])
        self.assertEqual(quiz['calibration']['mix'], {'mcq': 1, 'short_answer': 0})
        evaluated = self.post('rag/evaluate-quiz', {'topic': 'Search', 'quiz_id': quiz['quiz_id'],
            'given_answers': ['A sorted sequence']})
        self.assertEqual(evaluated['score'], 100)
        data = self.client.get('/api/learning/data').json()
        self.assertEqual(data['topics'][0]['recall']['method'], 'cold_start_heuristic')
        self.assertEqual(len(data['study_events']), 3)
        self.assertTrue(data['quizzes'])
        for endpoint in ['health', 'rag/topics', 'recommendations/smart', 'learning/topic-state?topic=Search', 'vectors/diagnostics']:
            self.assertEqual(self.client.get('/api/' + endpoint).status_code, 200, endpoint)
        self.post('settings/ai-config', {'provider': 'ollama', 'model': 'test-model'})
        self.post('settings/ai-config', {'provider': 'unsupported'}, code=422)
        for entry in data['history']:
            self.assertEqual(self.client.delete('/api/learning/history/' + entry['id']).status_code, 200)
        self.assertEqual(self.rag.count, 0)
        self.assertEqual(self.analytics.attempts(), [])

    def test_video_observation_speculation_and_durable_ai_job(self):
        doc = self.post('vectors/transcript', {'source_url': 'https://example.test/video', 'topic': 'Search',
            'captions': [{'start_ms': 0, 'end_ms': 1000, 'text': LESSON},
                         {'start_ms': 5000, 'end_ms': 6000, 'text': 'Future hidden secret is zephyr.'}]})['document_id']
        self.post('observation/intervals', {'document_id': doc, 'media_session_id': 'session-123',
            'event_sequence': 1, 'evidence': 'rendered-frame', 'observed_intervals': [{'start_ms': 0, 'end_ms': 1000}]})
        started = self.post('vectors/speculate', {'document_id': doc, 'position_ms': 1000,
            'idle': True, 'observed_only': True}, code=202)
        self.wait_job(started['job_id'])
        self.assertEqual(self.rag.count, 1)
        chunks = self.post('rag/retrieve', {'query': 'secret', 'document_id': doc})['chunks']
        self.assertNotIn('zephyr', str(chunks))
        request = {'operation': 'quiz', 'request_id': 'api-request-001', 'payload': {
            'topic': 'Search', 'source_type': 'video', 'document_id': doc, 'question_count': 1}}
        job = self.post('jobs', request, code=202)
        result = self.wait_job(job['job_id'])
        self.assertIn('quiz_id', result['result'])
        self.assertEqual(self.post('jobs', request, code=202)['job_id'], job['job_id'])
        self.assertEqual(self.client.delete('/api/vectors/documents/' + doc).status_code, 200)
        deleted_job = self.client.get('/api/jobs/' + job['job_id']).json()
        self.assertEqual(deleted_job['status'], 'failed')
        self.assertNotIn('result', deleted_job)

    def test_scoped_http_seal_observe_quiz_lease_and_restore(self):
        scope = {'learner_key': 'learner-http', 'video_key': 'youtube:http-test'}
        cues = [{'start': 0, 'end': 10, 'text': LESSON},
                {'start': 20, 'end': 21, 'text': 'Unwatched hidden secret is a copper lantern.'}]
        started = self.post('jobs', {'operation': 'seal', 'request_id': 'http-seal-001',
            'payload': {**scope, 'cues': cues, 'duration': 30}}, code=202)
        sealed = self.wait_job(started['job_id'])['result']
        self.assertGreater(sealed['sealed_added'], 0)
        self.assertEqual(sealed['counts'].get('ACTIVE', 0), 0)
        self.post('f1/intervals', {**scope, 'batch_seq': 1, 'revision': '0' * 64,
            'intervals': [{'start': 0, 'end': 10, 'wall_ms': 10000, 'rate': 1}]}, code=422)
        self.post('f1/intervals', {**scope, 'batch_seq': 1, 'revision': sealed['revision'],
            'intervals': [{'start': 0, 'end': 10, 'wall_ms': 10000, 'rate': 1}]})
        status = self.client.get('/api/f1/status').json()
        self.assertTrue(status['enabled'])
        self.assertGreater(status['scoped_counts'].get('ACTIVE', 0), 0)
        question = {**scope, 'source_type': 'video',
                    'question': 'How does binary search work?', 'top_k': 1,
                    'transcript_context': 'Unwatched hidden secret is a copper lantern.'}
        first = self.post('rag/ask', question)
        self.assertNotIn('copper lantern', str(first))
        self.assertEqual(self.post('rag/ask', question), first)
        summary = self.post('rag/summarize', {**scope, 'source_type': 'video',
            'topic': 'Binary search', 'page_content': 'Unwatched hidden secret is a copper lantern.'})
        self.assertNotIn('copper lantern', str(summary))
        quiz = self.post('rag/generate-quiz', {**scope, 'source_type': 'video',
            'topic': 'Binary search', 'question_count': 1})
        self.assertNotIn('answer', quiz['questions'][0])
        self.assertGreater(self.client.get('/api/f1/status').json()['open_leases'], 0)
        self.assertFalse(self.rag.scoped.retrieve(scope['learner_key'], scope['video_key'], 'binary search'))
        self.post('rag/evaluate-quiz', {'topic': 'Binary search', 'quiz_id': quiz['quiz_id'],
            'given_answers': ['A sorted sequence']})
        self.assertEqual(self.client.get('/api/f1/status').json()['open_leases'], 0)
        self.assertTrue(self.rag.scoped.retrieve(scope['learner_key'], scope['video_key'], 'binary search'))

    def test_invalid_inputs_and_missing_resources_are_handled(self):
        self.post('jobs', {'operation': 'quiz', 'payload': {'topic': 'Missing', 'question_count': 0}}, code=422)
        self.post('rag/ask', {'question': 'Test', 'source_type': 'video'}, code=422)
        self.post('rag/evaluate-quiz', {'topic': 'Missing', 'quiz_id': 'missing-id', 'given_answers': []}, code=404)
        self.assertEqual(self.client.get('/api/jobs/missing-id').status_code, 404)
        self.post('observation/intervals', {'document_id': 'missing', 'media_session_id': 'session-123',
            'event_sequence': 1, 'evidence': 'rendered-frame',
            'observed_intervals': [{'start_ms': 10, 'end_ms': 1}]}, code=422)

    def test_scoped_inputs_reject_ambiguous_keys_and_incomplete_scopes(self):
        scope = {'learner_key': 'learner-http', 'video_key': 'youtube:http-test'}
        seal = {**scope, 'duration': 10, 'cues': [{'start': 0, 'end': 1, 'text': LESSON}]}
        for fields in ({'learner_key': 'learner|youtube:other'}, {'video_key': 'youtube:a|b'},
                       {'video_key': 'youtube:'}, {'learner_key': ' '}, {'duration': 1e300}):
            with self.subTest(fields=fields):
                self.post('f1/seal', {**seal, **fields}, code=422)
        for fields in ({'learner_key': 'learner-http'}, {'video_key': 'youtube:http-test'},
                       {'learner_key': 'learner|other', 'video_key': 'youtube:http-test'}):
            with self.subTest(fields=fields):
                self.post('rag/ask', {'question': 'Explain this', 'source_type': 'video', **fields}, code=422)
        for seq in (True, 1.5, '1'):
            self.post('f1/intervals', {**scope, 'batch_seq': seq, 'revision': 'a' * 64, 'intervals': []}, code=422)
        self.post('f1/intervals', {**scope, 'batch_seq': 1, 'revision': 'a' * 64,
            'intervals': [{'start': 2, 'end': 1, 'wall_ms': 1000, 'rate': 1}]}, code=422)
        # JSON parsers may accept NaN; the runtime envelope must reject it.
        response = self.client.post('/api/runtime/player-state',
            content=json.dumps({**scope, 'state': 'PAUSED', 'media_time': float('nan'), 'ts': 0}),
            headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 422, response.text)
