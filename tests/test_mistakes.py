"""Review scheduling, migration, assessment capture, and lease-safe HTTP delivery."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from unittest.mock import patch

from sqlalchemy import create_engine, text
from ml.analytics import QuizAnalyticsStore
from ml.mistakes import MistakeNotebook
import test_api_features as api_fixture


WRONG = {'question': 'What sequence does binary search require?', 'given_answer': 'Unsorted',
         'expected_answer': 'Sorted', 'is_correct': False, 'explanation': 'Ordering makes the midpoint comparison meaningful.',
         'citations': ['evidence-one'], 'bloom_level': 'Remember'}


class MistakeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = create_engine(f'sqlite:///{(Path(self.temp.name) / "state.db").as_posix()}')
        self.analytics = QuizAnalyticsStore(engine=self.db)
        self.book = self.analytics.mistakes
        self.now = datetime(2026, 10, 2, tzinfo=timezone.utc)

    def tearDown(self):
        self.db.dispose()
        self.temp.cleanup()

    def record(self, details=None, topic='Search'):
        return self.analytics.record(topic, 0, 10, 8, 0, 1, details or [WRONG])

    def test_only_missed_complete_questions_create_cards_and_capture_is_idempotent(self):
        attempt = self.record([WRONG, {**WRONG, 'is_correct': True}, {'is_correct': False}])
        cards = self.book.list(include_scheduled=True)['items']
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]['detail']['expected_answer'], 'Sorted')
        with self.db.begin() as db:
            self.book.capture(db, attempt, 'Search', self.now.isoformat(), [WRONG])
        self.assertEqual(self.book.list(include_scheduled=True)['summary']['total'], 1)

    def test_new_attempt_and_card_are_atomic_when_capture_fails(self):
        with patch.object(self.book, 'capture', side_effect=OSError('storage failed')):
            with self.assertRaises(OSError):
                self.record()
        self.assertEqual(self.analytics.attempts(), [])
        self.assertEqual(self.book.list()['summary']['total'], 0)

    def test_again_remembered_spacing_and_version_conflicts(self):
        self.record()
        card = self.book.list(True)['items'][0]
        first = self.book.review(card['id'], 'remembered', 0, now=self.now)
        self.assertEqual(first['due_at'], (self.now + timedelta(days=1)).isoformat())
        with self.assertRaises(ValueError):
            self.book.review(card['id'], 'remembered', 0, now=self.now)
        second = self.book.review(card['id'], 'remembered', 1, now=self.now + timedelta(days=1))
        self.assertEqual(second['due_at'], (self.now + timedelta(days=4)).isoformat())
        reset = self.book.review(card['id'], 'again', 2, now=self.now + timedelta(days=4))
        self.assertEqual(reset['streak'], 0)
        self.assertEqual(reset['due_at'], (self.now + timedelta(days=4, minutes=10)).isoformat())
        for version, days in enumerate((1, 3, 7, 14, 30, 30), start=3):
            card = self.book.review(card['id'], 'remembered', version, now=self.now)
            self.assertEqual(card['due_at'], (self.now + timedelta(days=days)).isoformat())

    def test_due_filters_pagination_restart_and_topic_deletion(self):
        for index in range(23):
            self.record(topic='Search' if index < 22 else 'Stacks')
        first = self.book.list(True, limit=20)
        second = self.book.list(True, limit=20, offset=20)
        self.assertEqual(len(first['items']), 20)
        self.assertEqual(len(second['items']), 3)
        self.assertFalse({c['id'] for c in first['items']} & {c['id'] for c in second['items']})
        card = first['items'][0]
        future = datetime.now(timezone.utc) + timedelta(days=2)
        self.book.review(card['id'], 'remembered', 0, now=future)
        self.assertEqual(self.book.list()['summary']['due'], 22)
        restarted = QuizAnalyticsStore(engine=self.db)
        self.assertEqual(restarted.mistakes.get(card['id'])['version'], 1)
        self.assertEqual(restarted.mistakes.list(True)['summary']['total'], 23)
        restarted.delete_topics(['Search'])
        self.assertEqual(restarted.mistakes.list(True)['summary']['total'], 1)
        self.assertEqual(restarted.mistakes.list(True)['items'][0]['topic'], 'Stacks')

    def test_old_assessments_are_backfilled_once_without_resetting_reviews(self):
        self.record()
        with self.db.begin() as db:
            db.execute(text('DELETE FROM mistake_reviews'))
            db.execute(text("DELETE FROM learning_migrations WHERE name='mistake-notebook-v1'"))
        migrated = MistakeNotebook(self.db, RLock())
        card = migrated.list(True)['items'][0]
        migrated.review(card['id'], 'again', 0, now=self.now)
        migrated_again = MistakeNotebook(self.db, RLock())
        self.assertEqual(migrated_again.get(card['id'])['review_count'], 1)
        self.assertEqual(migrated_again.list(True)['summary']['total'], 1)


class MistakeAPITests(unittest.TestCase):
    setUp = api_fixture.APIFeaturesTests.setUp
    tearDown = api_fixture.APIFeaturesTests.tearDown
    post = api_fixture.APIFeaturesTests.post

    def test_wrong_quiz_capture_review_http_validation_and_no_mastery_change(self):
        indexed = self.post('rag/ingest', {'title': 'Search lesson', 'topic': 'Search', 'content': api_fixture.LESSON})
        quiz = self.post('rag/generate-quiz', {'topic': 'Search', 'document_id': indexed['document_id'], 'question_count': 1})
        evaluated = self.post('rag/evaluate-quiz', {'quiz_id': quiz['quiz_id'], 'topic': 'Search', 'given_answers': ['Wrong']})
        queue = self.client.get('/api/learning/mistakes').json()
        self.assertEqual(queue['summary']['due'], 1)
        card = queue['items'][0]
        self.assertEqual(card['expected_answer'], evaluated['evaluations'][0]['expected_answer'])
        self.assertNotIn('detail', card)
        self.assertNotIn('citations', card)
        self.assertNotIn('attempt_id', card)
        before = self.analytics.topic_summaries()
        path = f"learning/mistakes/{card['id']}/review"
        result = self.post(path, {'outcome': 'remembered', 'version': card['version']})
        self.assertEqual(result['review_count'], 1)
        self.assertEqual(self.client.get('/api/learning/mistakes').json()['items'], [])
        self.assertEqual(self.client.get('/api/learning/mistakes?include_scheduled=true').json()['total'], 1)
        self.assertEqual(self.analytics.topic_summaries(), before)
        self.post(path, {'outcome': 'again', 'version': card['version']}, code=409)
        for payload in ({'outcome': 'mastered', 'version': 1}, {'outcome': 'again', 'version': True},
                        {'outcome': 'again', 'version': -1}):
            self.post(path, payload, code=422)
        self.post('learning/mistakes/mistake_99999_0/review', {'outcome': 'again', 'version': 0}, code=404)
        self.assertEqual(self.client.get('/api/learning/mistakes?limit=101').status_code, 422)
        self.assertEqual(self.client.get('/api/learning/mistakes?offset=-1').status_code, 422)

    def test_held_evidence_hides_every_feedback_field_and_blocks_review_until_restoration(self):
        cues = [{'start': i, 'end': i + 1, 'text': f'Search lesson section {i} explains sorted binary lookup.'} for i in range(12)]
        seal = self.rag.scoped.seal('review-learner', 'youtube:review', cues, 12)
        self.rag.scoped.intervals('review-learner', 'youtube:review', 1,
            [{'start': 0, 'end': 12, 'wall_ms': 12000, 'rate': 1}], revision=seal['revision'])
        chunks = self.rag.scoped.retrieve('review-learner', 'youtube:review', 'Search')
        detail = {**WRONG, 'citations': [chunks[0]['chunk_id']]}
        self.analytics.record('Search', 0, 10, 8, 0, 1, [detail])
        self.rag.leases.open_scoped('active-review-quiz', 'review-learner', 'youtube:review',
                                    [{'citations': detail['citations']}])
        queue = self.client.get('/api/learning/mistakes').json()
        card = queue['items'][0]
        self.assertTrue(card['locked'])
        for key in ('question', 'given_answer', 'expected_answer', 'explanation', 'citations', 'detail'):
            self.assertNotIn(key, card)
        self.post(f"learning/mistakes/{card['id']}/review", {'outcome': 'again', 'version': 0}, code=409)
        self.rag.leases.close('active-review-quiz')
        visible = self.client.get('/api/learning/mistakes').json()['items'][0]
        self.assertFalse(visible['locked'])
        self.assertEqual(visible['expected_answer'], 'Sorted')
        self.post(f"learning/mistakes/{card['id']}/review", {'outcome': 'again', 'version': 0})

    def test_correct_quiz_does_not_add_cards_and_history_deletion_removes_saved_mistakes(self):
        indexed = self.post('rag/ingest', {'title': 'Search lesson', 'topic': 'Search', 'content': api_fixture.LESSON})
        for answer in ('A sorted sequence', 'Wrong'):
            quiz = self.post('rag/generate-quiz', {'topic': 'Search', 'document_id': indexed['document_id'], 'question_count': 1})
            self.post('rag/evaluate-quiz', {'quiz_id': quiz['quiz_id'], 'topic': 'Search', 'given_answers': [answer]})
        self.assertEqual(self.client.get('/api/learning/mistakes').json()['total'], 1)
        history = self.client.get('/api/learning/data').json()['history']
        self.assertEqual(self.client.delete('/api/learning/history/' + history[0]['id']).status_code, 200)
        self.assertEqual(self.client.get('/api/learning/mistakes?include_scheduled=true').json()['total'], 0)


if __name__ == '__main__':
    unittest.main()
