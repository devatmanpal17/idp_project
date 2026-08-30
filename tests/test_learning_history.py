import unittest
from unittest.mock import patch

from backend.routes import learning_data


def _records():
    return [
        {
            "chunk_id": "doc_one_0000",
            "document_id": "doc_one",
            "text": "Hash maps count each value efficiently.",
            "topic": "Top K Elements",
            "course": "Top K Elements lesson",
            "page_url": "https://example.com/lesson?utm_source=test",
            "source_type": "document",
            "ingested_at": "2026-08-30T10:00:00+00:00",
        },
        {
            "chunk_id": "doc_one_0001",
            "document_id": "doc_one",
            "text": "A heap keeps the largest frequencies.",
            "topic": "Top K Elements",
            "course": "Top K Elements lesson",
            "page_url": "https://example.com/lesson?utm_source=test",
            "source_type": "document",
            "ingested_at": "2026-08-30T10:00:00+00:00",
        },
        {
            "chunk_id": "doc_two_0000",
            "document_id": "doc_two",
            "text": "Bucket sorting is another valid approach.",
            "topic": "Top K Elements",
            "course": "Top K Elements lesson",
            "page_url": "https://example.com/lesson",
            "source_type": "document",
            "ingested_at": "2026-08-30T11:00:00+00:00",
        },
    ]


class LearningHistoryTests(unittest.TestCase):
    def test_history_groups_canonical_urls_and_complete_documents(self):
        documents = learning_data._document_catalogue(_records())
        history = learning_data._history_entries(documents)

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["page_url"], "https://example.com/lesson")
        self.assertEqual(history[0]["document_ids"], ["doc_one", "doc_two"])
        self.assertEqual(history[0]["indexed_chunks"], 3)
        self.assertEqual(history[0]["visit_count"], 2)

    def test_learning_data_generates_plan_and_initial_recommendation(self):
        with (
            patch.object(learning_data.rag_engine, "catalogue_records", _records),
            patch.object(learning_data.quiz_analytics, "attempts", return_value=[]),
            patch.object(learning_data.quiz_analytics, "topic_summaries", return_value=[]),
        ):
            result = learning_data.build_learning_data()

        self.assertEqual(len(result["topics"]), 1)
        self.assertEqual(len(result["study_events"]), 3)
        self.assertEqual(result["study_events"][0]["event_type"], "quiz")
        self.assertEqual(result["recommendations"][0]["type"], "initial_assessment")
        self.assertEqual(
            result["courses"][0]["source_url"], "https://example.com/lesson"
        )

    def test_deleting_history_removes_rag_and_orphaned_assessments(self):
        documents = learning_data._document_catalogue(_records())
        history_id = learning_data._history_entries(documents)[0]["id"]
        deleted_topics = []

        def delete_topics(topics):
            deleted_topics.extend(topics)
            return {"quiz_attempts": 1, "generated_quizzes": 1}

        with (
            patch.object(learning_data.rag_engine, "catalogue_records", _records),
            patch.object(
                learning_data.rag_engine,
                "delete_documents",
                side_effect=lambda ids: len(ids) + 1,
            ),
            patch.object(learning_data.rag_engine, "topics", return_value=[]),
            patch.object(
                learning_data.quiz_analytics,
                "delete_topics",
                side_effect=delete_topics,
            ),
        ):
            result = learning_data.delete_history_entry(history_id)

        self.assertEqual(result["removed_documents"], 2)
        self.assertEqual(result["removed_chunks"], 3)
        self.assertEqual(result["removed_topics"], ["Top K Elements"])
        self.assertEqual(deleted_topics, ["Top K Elements"])


if __name__ == "__main__":
    unittest.main()
