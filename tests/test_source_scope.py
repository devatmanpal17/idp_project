import unittest

from fastapi import HTTPException

from backend.models import GenerateQuizRequest
from backend.routes.rag import generate_quiz


class SourceScopeTests(unittest.TestCase):
    def test_video_quiz_fails_before_generation_when_captions_are_too_short(self):
        request = GenerateQuizRequest(
            topic="Current video",
            source_type="video",
            observed_until_seconds=12,
            source_context="[0:01] Only a few caption words have appeared so far.",
            question_count=3,
        )

        with self.assertRaises(HTTPException) as raised:
            generate_quiz(request)

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("caption words", str(raised.exception.detail))


if __name__ == "__main__":
    unittest.main()
