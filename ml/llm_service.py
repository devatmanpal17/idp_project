"""
Cognivue ML — LLM Service
Multi-provider LLM generation and evaluation engine.

Priority order:
1. OpenAI (GPT-4o-mini) — preferred
2. Google Gemini (gemini-2.0-flash)
3. Local RAG-grounded generator (zero-key fallback)

All quiz generation and evaluation goes through the LLM when a key is available.
"""

import os
import json
import random
import traceback
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional

from .calibration import compute_mastery_update


class LLMService:
    def __init__(self):
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
        self.openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        self.preferred_provider = os.environ.get("AI_PROVIDER", "auto")
        self._last_provider_used = "none"

    @property
    def active_provider(self) -> str:
        """Returns the provider that will actually be used."""
        if self.openai_api_key:
            return "openai"
        if self.gemini_api_key:
            return "gemini"
        return "local_rag_engine"

    def configure(self, provider: str, api_key: str):
        """Update API configuration at runtime."""
        self.preferred_provider = provider
        if provider == "gemini":
            self.gemini_api_key = api_key
        elif provider == "openai":
            self.openai_api_key = api_key

    # ── Quiz Generation ─────────────────────────────────────────────

    def generate_quiz_with_rag(
        self,
        topic: str,
        context_chunks: List[Dict[str, Any]],
        mastery_score: float,
        difficulty: float,
        count: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Generate structured quiz questions grounded in retrieved RAG context chunks.
        Tries real LLM providers first, falls back to local only if no key available.
        """
        # Try OpenAI first (preferred)
        if self.openai_api_key and self.preferred_provider in ["auto", "openai"]:
            try:
                result = self._call_openai_quiz(topic, context_chunks, mastery_score, difficulty, count)
                if result:
                    self._last_provider_used = "openai/gpt-4o-mini"
                    print(f"[LLM] [OK] Generated {len(result)} questions via OpenAI GPT-4o-mini")
                    return result
            except Exception as e:
                print(f"[LLM] OpenAI quiz generation error: {e}")

        # Try Gemini
        if self.gemini_api_key and self.preferred_provider in ["auto", "gemini"]:
            try:
                result = self._call_gemini_quiz(topic, context_chunks, mastery_score, difficulty, count)
                if result:
                    self._last_provider_used = "gemini/gemini-2.0-flash"
                    print(f"[LLM] [OK] Generated {len(result)} questions via Gemini 2.0 Flash")
                    return result
            except Exception as e:
                print(f"[LLM] Gemini quiz generation error: {e}")

        # Local fallback
        self._last_provider_used = "local_rag_engine"
        print(f"[LLM] Using local RAG engine (no API keys configured)")
        return self._generate_local_quiz(topic, context_chunks, difficulty, count)

    # ── Quiz Evaluation ──────────────────────────────────────────────

    def evaluate_quiz(
        self,
        questions: List[Dict[str, Any]],
        given_answers: List[str],
        current_mastery: float
    ) -> Dict[str, Any]:
        """
        Evaluates student responses. Uses LLM for detailed feedback when available,
        falls back to exact-match grading otherwise.
        """
        # Try LLM-powered evaluation
        if self.openai_api_key:
            try:
                result = self._call_openai_evaluate(questions, given_answers, current_mastery)
                if result:
                    print(f"[LLM] [OK] Evaluated quiz via OpenAI GPT-4o-mini")
                    return result
            except Exception as e:
                print(f"[LLM] OpenAI evaluation error: {e}, using local grading")

        if self.gemini_api_key:
            try:
                result = self._call_gemini_evaluate(questions, given_answers, current_mastery)
                if result:
                    print(f"[LLM] [OK] Evaluated quiz via Gemini")
                    return result
            except Exception as e:
                print(f"[LLM] Gemini evaluation error: {e}, using local grading")

        # Local exact-match grading
        return self._evaluate_local(questions, given_answers, current_mastery)

    # ── OpenAI Implementation ────────────────────────────────────────

    def _call_openai_quiz(
        self,
        topic: str,
        chunks: List[Dict[str, Any]],
        mastery_score: float,
        difficulty: float,
        count: int
    ) -> Optional[List[Dict[str, Any]]]:
        """Generate quiz questions via OpenAI GPT-4o-mini with RAG context."""
        context_text = "\n\n".join([
            f"[{c.get('chunk_id', 'chunk')}] (similarity={c.get('similarity', 0):.3f}) {c.get('snippet', '')}"
            for c in chunks
        ])

        system_prompt = """You are Cognivue's AI learning assessment engine. You generate rigorous, pedagogically-grounded quiz questions based strictly on provided lecture transcript chunks retrieved via RAG vector search.

Rules:
- Questions MUST test understanding of concepts from the provided context chunks
- Each question must have exactly 4 choices with only one correct answer
- The "why" field must explain WHY the answer is correct, citing specific concepts from the context
- Difficulty scales from 0.0 (basic recall) to 1.0 (advanced synthesis/application)
- At difficulty > 0.6, include questions that require combining multiple concepts
- At difficulty < 0.4, focus on direct comprehension and terminology
- NEVER generate trivially obvious or trick questions
- Return ONLY a valid JSON array, no markdown formatting"""

        user_prompt = f"""Generate exactly {count} adaptive assessment questions for the topic "{topic}".

Learner Profile:
- Current mastery score: {mastery_score}/100
- Target difficulty: {difficulty:.2f} (0.0=basic recall, 1.0=advanced synthesis)
- {"Focus on foundational concepts" if difficulty < 0.4 else "Focus on application and analysis" if difficulty < 0.7 else "Focus on synthesis, evaluation, and edge cases"}

Retrieved RAG Context Chunks:
{context_text}

Return a JSON array of exactly {count} question objects:
[
  {{
    "q": "Clear, specific question text that tests understanding",
    "choices": ["Option A", "Option B", "Option C", "Option D"],
    "answer": "The exact text of the correct option",
    "why": "Pedagogical explanation of why this is correct, referencing the context"
  }}
]"""

        return self._openai_request(system_prompt, user_prompt)

    def _call_openai_evaluate(
        self,
        questions: List[Dict[str, Any]],
        given_answers: List[str],
        current_mastery: float
    ) -> Optional[Dict[str, Any]]:
        """Evaluate quiz answers via OpenAI with detailed pedagogical feedback."""
        qa_pairs = []
        for i, (q, ans) in enumerate(zip(questions, given_answers)):
            qa_pairs.append(f"Q{i+1}: {q.get('q', '')}\nCorrect Answer: {q.get('answer', '')}\nStudent Answer: {ans}")

        system_prompt = """You are Cognivue's AI assessment grader. Evaluate student quiz answers with detailed pedagogical feedback. Be fair but rigorous — partial credit is acceptable for answers that demonstrate understanding even if not exact matches."""

        user_prompt = f"""Grade these quiz answers. Current mastery: {current_mastery}/100.

{chr(10).join(qa_pairs)}

Return a JSON object:
{{
  "score": <percentage 0-100>,
  "correct_count": <integer>,
  "total_questions": {len(questions)},
  "evaluations": [
    {{
      "question": "question text",
      "given_answer": "student's answer",
      "expected_answer": "correct answer",
      "is_correct": true/false,
      "explanation": "Why correct/incorrect, what the student should understand"
    }}
  ],
  "previous_mastery": {current_mastery},
  "new_mastery": <calculated new mastery>,
  "mastery_delta": <change in mastery>,
  "feedback_summary": "Overall performance summary with specific study recommendations"
}}"""

        result = self._openai_request(system_prompt, user_prompt, expect_object=True)
        if result and isinstance(result, dict):
            return result
        return None

    def _openai_request(
        self,
        system_prompt: str,
        user_prompt: str,
        expect_object: bool = False
    ) -> Any:
        """Make a direct HTTP request to OpenAI API."""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.openai_api_key}"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": {"type": "json_object"} if expect_object else {"type": "text"},
            "temperature": 0.35,
            "max_tokens": 4096,
        }

        # For array responses, we need json_object wrapping
        if not expect_object:
            payload["response_format"] = {"type": "text"}

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            content = res_data["choices"][0]["message"]["content"]

            # Clean markdown code fences if present
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            parsed = json.loads(content)

            if expect_object:
                if isinstance(parsed, dict):
                    # Handle wrapper like {"questions": [...]}
                    if "questions" in parsed and isinstance(parsed["questions"], list):
                        return parsed
                    return parsed
            else:
                if isinstance(parsed, list):
                    return parsed
                if isinstance(parsed, dict) and "questions" in parsed:
                    return parsed["questions"]

            return parsed

    # ── Gemini Implementation ────────────────────────────────────────

    def _call_gemini_quiz(
        self,
        topic: str,
        chunks: List[Dict[str, Any]],
        mastery_score: float,
        difficulty: float,
        count: int
    ) -> Optional[List[Dict[str, Any]]]:
        """Generate quiz questions via Google Gemini with RAG context."""
        context_text = "\n\n".join([
            f"[{c.get('chunk_id', 'chunk')}] (sim={c.get('similarity', 0):.3f}) {c.get('snippet', '')}"
            for c in chunks
        ])

        prompt = f"""You are Cognivue's AI learning tutor. Generate {count} high-quality adaptive quiz questions for "{topic}".

Learner mastery: {mastery_score}/100. Target difficulty: {difficulty:.2f}.
{"Focus on recall" if difficulty < 0.4 else "Focus on application" if difficulty < 0.7 else "Focus on synthesis and edge cases"}.

Retrieved lecture transcript context:
{context_text}

Return a JSON array:
[
  {{
    "q": "Question text",
    "choices": ["A", "B", "C", "D"],
    "answer": "Correct choice text",
    "why": "Explanation citing the context"
  }}
]"""

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.4
            }
        }

        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=20) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"]
            questions = json.loads(raw_text)
            if isinstance(questions, list) and len(questions) > 0:
                return questions
        return None

    def _call_gemini_evaluate(
        self,
        questions: List[Dict[str, Any]],
        given_answers: List[str],
        current_mastery: float
    ) -> Optional[Dict[str, Any]]:
        """Evaluate quiz via Gemini."""
        qa_pairs = []
        for i, (q, ans) in enumerate(zip(questions, given_answers)):
            qa_pairs.append(f"Q{i+1}: {q.get('q', '')}\nCorrect: {q.get('answer', '')}\nStudent: {ans}")

        prompt = f"""Grade these quiz answers. Current mastery: {current_mastery}/100.

{chr(10).join(qa_pairs)}

Return JSON object with: score (0-100), correct_count, total_questions, evaluations array (question, given_answer, expected_answer, is_correct, explanation), previous_mastery, new_mastery, mastery_delta, feedback_summary."""

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.2
            }
        }

        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=20) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"]
            result = json.loads(raw_text)
            if isinstance(result, dict):
                return result
        return None

    # ── Local Fallback ───────────────────────────────────────────────

    def _generate_local_quiz(
        self,
        topic: str,
        chunks: List[Dict[str, Any]],
        difficulty: float,
        count: int
    ) -> List[Dict[str, Any]]:
        """
        Local RAG-grounded quiz generator — synthesizes questions directly from
        retrieved transcript chunks. Used only when no API key is configured.
        """
        synthesized: List[Dict[str, Any]] = []

        for i, c in enumerate(chunks[:count]):
            snippet = c.get("snippet", "")
            words = snippet.split()

            # Extract a key phrase from the snippet for distractor generation
            key_phrase = " ".join(words[:12]) if len(words) > 12 else snippet

            synthesized.append({
                "q": f"Based on the lecture content for {topic}, which of the following statements is accurate?",
                "choices": [
                    f"{snippet[:120]}{'...' if len(snippet) > 120 else ''}",
                    f"The {topic} algorithm requires O(n!) time complexity in all cases",
                    f"All parameters in {topic} are determined by random initialization only",
                    f"The mathematical foundation of {topic} has been disproven in recent literature"
                ],
                "answer": f"{snippet[:120]}{'...' if len(snippet) > 120 else ''}",
                "why": f"This is directly stated in the lecture transcript (chunk {c.get('chunk_id', 'unknown')}, similarity {c.get('similarity', 0):.3f}): \"{snippet}\""
            })

        if not synthesized:
            synthesized.append({
                "q": f"What is the foundational requirement for understanding {topic}?",
                "choices": [
                    "Building theoretical foundations with empirical application",
                    "Memorizing isolated terminology without context",
                    "Disregarding prerequisite mathematical assumptions",
                    "Restricting evaluation to the training set only"
                ],
                "answer": "Building theoretical foundations with empirical application",
                "why": "Deep comprehension requires connecting theory to practice through structured retrieval."
            })

        return synthesized[:count]

    def _evaluate_local(
        self,
        questions: List[Dict[str, Any]],
        given_answers: List[str],
        current_mastery: float
    ) -> Dict[str, Any]:
        """Local exact-match evaluation with mastery update."""
        results = []
        correct_count = 0

        for q, given in zip(questions, given_answers):
            expected = q.get("answer", "")
            is_correct = (
                given.strip().lower() == expected.strip().lower() or
                (len(given) > 10 and (
                    given.strip().lower() in expected.strip().lower() or
                    expected.strip().lower() in given.strip().lower()
                ))
            )
            if is_correct:
                correct_count += 1

            results.append({
                "question": q.get("q", ""),
                "given_answer": given,
                "expected_answer": expected,
                "is_correct": is_correct,
                "explanation": q.get("why", "Review the lecture transcript for this concept.")
            })

        total = len(questions) or 1
        score_pct = round((correct_count / total) * 100, 1)
        mastery_info = compute_mastery_update(score_pct, current_mastery)

        return {
            "score": score_pct,
            "correct_count": correct_count,
            "total_questions": total,
            "evaluations": results,
            "previous_mastery": current_mastery,
            "new_mastery": mastery_info["new_mastery"],
            "mastery_delta": mastery_info["mastery_delta"],
            "feedback_summary": (
                "Outstanding comprehension! Concepts solidified."
                if score_pct >= 80
                else "Good effort. Review the explanations on missed concepts."
                if score_pct >= 50
                else "Needs reinforcement. A study block has been added to your plan."
            )
        }


# Global Singleton
llm_service = LLMService()
