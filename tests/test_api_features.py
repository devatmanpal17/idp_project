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
from sqlalchemy import create_engine
from backend.routes import rag, vectors, jobs, learning_data, settings, health, recommendations
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
        for module in [rag, vectors, jobs, learning_data, settings, health, recommendations]:
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

    def test_invalid_inputs_and_missing_resources_are_handled(self):
        self.post('jobs', {'operation': 'quiz', 'payload': {'topic': 'Missing', 'question_count': 0}}, code=422)
        self.post('rag/ask', {'question': 'Test', 'source_type': 'video'}, code=422)
        self.post('rag/evaluate-quiz', {'topic': 'Missing', 'quiz_id': 'missing-id', 'given_answers': []}, code=404)
        self.assertEqual(self.client.get('/api/jobs/missing-id').status_code, 404)
        self.post('observation/intervals', {'document_id': 'missing', 'media_session_id': 'session-123',
            'event_sequence': 1, 'evidence': 'rendered-frame',
            'observed_intervals': [{'start_ms': 10, 'end_ms': 1}]}, code=422)
