import unittest
from unittest.mock import Mock

from ml.llm_service import LLMService


class ChatAssistantTests(unittest.TestCase):
    def test_greeting_uses_fast_conversational_response(self):
        service = LLMService()
        service._chat = Mock(side_effect=AssertionError("the model should not run"))

        answer = service.answer_with_rag("Hi, how are you?", [])

        self.assertIn("doing well", answer)
        service._chat.assert_not_called()

    def test_previous_turns_are_forwarded_to_the_model(self):
        service = LLMService()
        service._chat = Mock(return_value="A stack follows LIFO order [E1].")
        chunks = [
            {
                "chunk_id": "E1",
                "source": "Data structures",
                "snippet": "A stack follows last-in, first-out (LIFO) order.",
            }
        ]
        history = [
            {"role": "user", "content": "Teach me about stacks."},
            {"role": "assistant", "content": "A stack is a data structure."},
        ]

        answer = service.answer_with_rag(
            "What order does it use?", chunks, history=history
        )

        self.assertEqual(answer, "A stack follows LIFO order [E1].")
        self.assertEqual(service._chat.call_args.kwargs["history"], history)


if __name__ == "__main__":
    unittest.main()
