import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from ml.vector_cache import VectorCache
from ml.recall import RecallModel
from ml.llm_service import LLMService, LLMConfigurationError, QuizQuestion, _quote_catalog
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

    def test_recall_priority_controls_admission_and_eviction(self):
        cache = VectorCache(max_bytes=35, ttl_seconds=10, clock=lambda: 0)
        self.assertTrue(cache.put('low', {'v': 'one'}, priority=.2))
        self.assertTrue(cache.put('high', {'v': 'two'}, priority=.9))
        # A well-recalled topic must not displace a topic more likely to need review.
        self.assertFalse(cache.put('new', {'v': 'xxx'}, priority=.1))
        self.assertIsNotNone(cache.get('low'))
        self.assertIsNotNone(cache.get('high'))
        self.assertTrue(cache.put('new', {'v': 'xxx'}, priority=.8))
        self.assertIsNone(cache.get('low'))
        self.assertIsNotNone(cache.get('high'))
        self.assertIsNotNone(cache.get('new'))
        self.assertLessEqual(cache.resident_bytes, 35)


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
    def test_generation_grammar_resolves_answer_labels_and_only_allows_active_citations(self):
        question = copy.deepcopy(VALID['questions'][0])
        question.update(answer='A', citations=['C1'])
        calls = []
        service = LLMService()
        def chat(_system, prompt, **kwargs):
            calls.append((prompt, kwargs['schema']))
            return json.dumps({'questions': [question]})
        service._chat = chat
        result = service.generate_quiz_with_rag('Search', CHUNKS, 50, .5, 1)
        self.assertEqual(result[0]['answer'], question['choices'][0])
        self.assertEqual(result[0]['citations'], ['E1'])
        properties = calls[0][1]['$defs']['QuizQuestion']['properties']
        self.assertEqual(properties['answer']['enum'], ['A', 'B', 'C', 'D'])
        self.assertEqual(properties['citations']['items']['enum'], ['C1'])

    def test_macro_quote_catalog_keeps_facts_from_the_end_of_the_evidence(self):
        sentences = [f'Lesson introduction number {index} describes a separate source fact.' for index in range(9)]
        sentences.append('A queue processes elements in their arrival order.')
        quotes = _quote_catalog([{'chunk_id': 'C1', 'snippet': ' '.join(sentences)}])['C1']
        self.assertEqual(len(quotes), 6)
        self.assertIn(sentences[0], quotes)
        self.assertIn(sentences[-1], quotes)

    def test_repair_guides_the_model_to_unused_facts_without_rewriting_accepted_questions(self):
        first = copy.deepcopy(VALID['questions'][0])
        first['evidence_quote'] = 'Binary search works on a sorted sequence.'
        next_fact = 'Binary search cuts the search interval in half.'
        chunks = [{'chunk_id': 'E1', 'snippet': first['evidence_quote'] + ' ' + next_fact}]
        invalid = {**first, 'answer': 'This answer is not one of the choices'}
        replacement = {**first, 'q': 'How does binary search reduce its search interval?',
                       'choices': ['It cuts the interval in half', 'It scans every queue', 'It empties a stack', 'It sorts a graph'],
                       'answer': 'It cuts the interval in half', 'evidence_quote': next_fact}
        responses = iter([{'questions': [first, invalid]}, {'questions': [replacement]}])
        calls = []
        service = LLMService()
        def chat(_system, prompt, **kwargs):
            calls.append((prompt, kwargs['schema']))
            return json.dumps(next(responses))
        service._chat = chat
        result = service.generate_quiz_with_rag('Search', chunks, 50, .5, 2)
        self.assertEqual(result, [first, replacement])
        self.assertEqual(calls[1][1]['$defs']['QuizQuestion']['properties']['evidence_quote']['enum'], [next_fact])
        self.assertIn(first['answer'], calls[1][0])

    def test_duplicate_repair_cannot_repeat_its_rejected_quote_on_the_next_attempt(self):
        first = copy.deepcopy(VALID['questions'][0])
        first['evidence_quote'] = 'Binary search works on a sorted sequence.'
        other = 'Binary search compares the middle value with the target.'
        last = 'Binary search cuts the search interval in half.'
        chunks = [{'chunk_id': 'E1', 'snippet': ' '.join([first['evidence_quote'], other, last])}]
        invalid = {**first, 'answer': 'Invalid answer text'}
        duplicate = {**first, 'evidence_quote': other}
        replacement = {**first, 'q': 'How does binary search reduce its search interval?',
                       'choices': ['It cuts the interval in half', 'It scans every queue', 'It empties a stack', 'It sorts a graph'],
                       'answer': 'It cuts the interval in half', 'evidence_quote': last}
        responses = iter([{'questions': [first, invalid]}, {'questions': [duplicate]}, {'questions': [replacement]}])
        schemas = []
        service = LLMService()
        def chat(*args, **kwargs):
            schemas.append(kwargs['schema'])
            return json.dumps(next(responses))
        service._chat = chat
        self.assertEqual(service.generate_quiz_with_rag('Search', chunks, 50, .5, 2), [first, replacement])
        self.assertEqual(schemas[2]['$defs']['QuizQuestion']['properties']['evidence_quote']['enum'], [last])

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

    def test_quiz_schema_offers_verbatim_source_quotes(self):
        question = copy.deepcopy(VALID['questions'][0])
        question['citations'] = ['C1']
        question['evidence_quote'] = CHUNKS[0]['snippet']
        service = LLMService()
        schemas = []
        def chat(_system, _prompt, **kwargs):
            schemas.append(kwargs['schema'])
            return json.dumps({'questions': [question]})
        service._chat = chat
        result = service.generate_quiz_with_rag('Search', CHUNKS, 50, .5, 1)
        options = schemas[0]['$defs']['QuizQuestion']['properties']['evidence_quote']['enum']
        self.assertIn(CHUNKS[0]['snippet'], options)
        self.assertEqual(result[0]['evidence_quote'], CHUNKS[0]['snippet'])

    def test_quote_cannot_be_assembled_across_two_citations(self):
        bad = copy.deepcopy(VALID)
        bad['questions'][0]['citations'] = ['A', 'B']
        chunks = [{'chunk_id': 'A', 'snippet': 'Binary search works on'},
                  {'chunk_id': 'B', 'snippet': 'a sorted sequence'}]
        service = LLMService()
        service._chat = lambda *args, **kwargs: json.dumps(bad)
        with self.assertRaises(LLMConfigurationError):
            service.generate_quiz_with_rag('Search', chunks, 50, .5, 1)
