import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from ml.vector_cache import VectorCache
from ml.recall import RecallModel
from ml.llm_service import LLMService, LLMConfigurationError, QuizQuestion
from test_quiz_guardrails import CHUNKS, VALID


class CacheTests(unittest.TestCase):
    def test_eviction_expiry_budget_and_defensive_copies(self):
        now = [0]
        cache = VectorCache(max_bytes=45, ttl_seconds=10, clock=lambda: now[0])
        self.assertTrue(cache.put('a', {'text': 'one'}))
        self.assertTrue(cache.put('b', {'text': 'two'}))
        cache.get('a')['text'] = 'tampered'
        self.assertEqual(cache.get('a')['text'], 'one')
        cache.put('c', {'text': 'three'})
        self.assertIsNone(cache.get('b'))
        self.assertLessEqual(cache.resident_bytes, 45)
        self.assertFalse(cache.put('large', 'x' * 100))
        now[0] = 11
        self.assertIsNone(cache.get('a'))
        self.assertEqual(cache.resident_bytes, 0)


class RecallTests(unittest.TestCase):
    def test_cold_start_and_unassessed_forecast(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        model = RecallModel([{'topic': 'Math', 'score': 80, 'completed_at': now.isoformat()}])
        self.assertIsNone(model.forecast('New', now)['probability'])
        forecast = model.forecast('Math', now)
        self.assertEqual(forecast['method'], 'cold_start_heuristic')
        self.assertEqual(forecast['probability'], .8)
        self.assertGreater(forecast['curve'][0]['retention'], forecast['curve'][-1]['retention'])
        self.assertFalse(model.diagnostics()['trained'])

    def test_training_uses_previous_outcomes_and_time_monotonicity(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        attempts = [{'topic': 'Math', 'score': 30 + (i % 4) * 20,
                     'completed_at': (now + timedelta(days=i)).isoformat()} for i in range(30)]
        model = RecallModel(list(reversed(attempts)))
        self.assertTrue(model.diagnostics()['trained'])
        self.assertEqual(len(model.samples), 29)
        self.assertEqual(model.samples[0][0][1], .3)
        self.assertEqual(model.samples[0][1], .5)
        self.assertGreater(model.probability(.8, 1), model.probability(.8, 10))
        self.assertTrue(all(0 <= model.probability(.5, day) <= 1 for day in range(50)))


class SelectiveRepairTests(unittest.TestCase):
    def test_answer_label_normalization_rejects_contradictory_text(self):
        question = copy.deepcopy(VALID['questions'][0])
        for answer in ['A', 'A. A sorted sequence', ' a sorted sequence ']:
            question['answer'] = answer
            self.assertEqual(QuizQuestion.model_validate(question).answer, 'A sorted sequence')
        question['answer'] = 'A. An unrelated answer'
        with self.assertRaises(ValueError):
            QuizQuestion.model_validate(question)

    def test_valid_question_survives_and_only_bad_slot_is_regenerated(self):
        first = copy.deepcopy(VALID['questions'][0])
        invalid = copy.deepcopy(first)
        invalid['citations'] = ['foreign-source']
        replacement = copy.deepcopy(first)
        replacement.update(q='How does binary search reduce the search interval?',
                           choices=['It cuts the search interval in half', 'It sorts a graph', 'It empties a stack', 'It doubles the interval'],
                           answer='It cuts the search interval in half')
        responses = iter([json.dumps({'questions': [first, invalid]}), json.dumps({'questions': [replacement]})])
        requested = []
        service = LLMService()
        def chat(*args, **kwargs):
            requested.append(kwargs['schema']['properties']['questions']['maxItems'])
            return next(responses)
        service._chat = chat
        result = service.generate_quiz_with_rag('Search', CHUNKS, 50, .5, 2)
        self.assertEqual(requested, [2, 1])
        self.assertEqual(result[0], first)
        self.assertEqual(result[1], replacement)

    def test_prompt_local_citation_is_resolved_to_real_chunk(self):
        question = copy.deepcopy(VALID['questions'][0])
        question['citations'] = ['C1']
        service = LLMService()
        prompts = []
        def chat(_system, prompt, **_kwargs):
            prompts.append(prompt)
            return json.dumps({'questions': [question]})
        service._chat = chat
        result = service.generate_quiz_with_rag('Search', CHUNKS, 50, .5, 1)
        self.assertIn('C1', prompts[0])
        self.assertEqual(result[0]['citations'], ['E1'])

    def test_quote_cannot_be_assembled_across_two_citations(self):
        bad = copy.deepcopy(VALID)
        bad['questions'][0]['citations'] = ['A', 'B']
        chunks = [{'chunk_id': 'A', 'snippet': 'Binary search works on'},
                  {'chunk_id': 'B', 'snippet': 'a sorted sequence'}]
        service = LLMService()
        service._chat = lambda *args, **kwargs: json.dumps(bad)
        with self.assertRaises(LLMConfigurationError):
            service.generate_quiz_with_rag('Search', chunks, 50, .5, 1)
