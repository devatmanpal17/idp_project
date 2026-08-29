import json
import unittest

from ml.llm_service import LLMConfigurationError, LLMService


CHUNKS = [
    {
        "chunk_id": "E1",
        "source": "Test source",
        "snippet": "Binary search works on a sorted sequence and repeatedly cuts the search interval in half.",
    }
]

VALID = {
    "questions": [
        {
            "q": "What type of sequence does binary search require?",
            "choices": ["A sorted sequence", "A random graph", "An empty stack", "An unsorted queue"],
            "answer": "A sorted sequence",
            "why": "The source states that binary search works on sorted data.",
            "citations": ["E1"],
            "evidence_quote": "Binary search works on a sorted sequence",
            "bloom_level": "Remember",
        }
    ]
}

HINDI = {
    "questions": [
        {
            "q": "बाइनरी खोज के लिए क्या आवश्यक है?",
            "choices": ["क्रमबद्ध सूची", "ग्राफ", "कतार", "स्टैक"],
            "answer": "क्रमबद्ध सूची",
            "why": "स्रोत यही बताता है।",
            "citations": ["E1"],
            "evidence_quote": "Binary search works on a sorted sequence",
            "bloom_level": "Remember",
        }
    ]
}


class QuizGuardrailTests(unittest.TestCase):
    def test_retries_hindi_then_accepts_grounded_english(self):
        service = LLMService()
        responses = iter([json.dumps(HINDI, ensure_ascii=True), json.dumps(VALID)])
        service._chat = lambda *args, **kwargs: next(responses)

        questions = service.generate_quiz_with_rag("Binary search", CHUNKS, 0, 0.3, 1)

        self.assertEqual(questions[0]["answer"], "A sorted sequence")

    def test_fails_closed_when_every_attempt_is_hindi(self):
        service = LLMService()
        service._chat = lambda *args, **kwargs: json.dumps(HINDI, ensure_ascii=True)

        with self.assertRaises(LLMConfigurationError):
            service.generate_quiz_with_rag("Binary search", CHUNKS, 0, 0.3, 1)

    def test_rejects_quote_that_is_not_in_cited_evidence(self):
        service = LLMService()
        invalid = json.loads(json.dumps(VALID))
        invalid["questions"][0]["evidence_quote"] = "This sentence was invented by the model"
        service._chat = lambda *args, **kwargs: json.dumps(invalid)

        with self.assertRaises(LLMConfigurationError):
            service.generate_quiz_with_rag("Binary search", CHUNKS, 0, 0.3, 1)


if __name__ == "__main__":
    unittest.main()
