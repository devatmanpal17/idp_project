"""Grounded quiz and answer generation through a local Ollama Llama model."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator


class LLMConfigurationError(RuntimeError):
    """Raised when Ollama or the configured model is unavailable."""


class QuizQuestion(BaseModel):
    q: str = Field(min_length=8)
    choices: List[str] = Field(min_length=4, max_length=4)
    answer: str
    why: str = Field(min_length=8)
    citations: List[str] = Field(min_length=1)
    bloom_level: Literal["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"]

    @field_validator("choices")
    @classmethod
    def distinct_choices(cls, value: List[str]) -> List[str]:
        if len({choice.strip().casefold() for choice in value}) != 4:
            raise ValueError("choices must be distinct")
        return value

    @field_validator("answer")
    @classmethod
    def answer_is_choice(cls, value: str, info: Any) -> str:
        choices = info.data.get("choices", [])
        if choices and value not in choices:
            raise ValueError("answer must exactly match one choice")
        return value


class QuizPayload(BaseModel):
    questions: List[QuizQuestion]


class LLMService:
    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.model = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2:3b")
        self.preferred_provider = "ollama"
        self._last_provider_used = "none"

    @property
    def active_provider(self) -> str:
        return f"Ollama / {self.model}"

    def configure(self, provider: str, api_key: str = "", model: str = "") -> None:
        if provider not in {"ollama", "local"}:
            raise ValueError("This deployment uses the local Ollama provider.")
        self.preferred_provider = "ollama"
        if model:
            self.model = model

    def status(self) -> Dict[str, Any]:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            names = [model.get("name", "") for model in payload.get("models", [])]
            ready = any(name == self.model or name.startswith(f"{self.model}:") for name in names)
            return {"online": True, "model": self.model, "model_ready": ready, "models": names}
        except Exception:
            return {"online": False, "model": self.model, "model_ready": False, "models": []}

    def _chat(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Dict[str, Any] | None = None,
    ) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.1},
            "keep_alive": "10m",
        }
        if schema:
            payload["format"] = schema
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMConfigurationError(f"Ollama rejected the request: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LLMConfigurationError(
                f"Ollama is unavailable. Start it and run `ollama pull {self.model}`."
            ) from exc
        content = result.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMConfigurationError("Ollama returned an empty completion.")
        self._last_provider_used = self.active_provider
        return content.strip()

    @staticmethod
    def _context(context_chunks: List[Dict[str, Any]]) -> str:
        return "\n\n".join(
            f"[{chunk['chunk_id']}] Source: {chunk.get('source') or chunk.get('course') or 'lesson'}\n"
            f"{chunk.get('snippet', '')}"
            for chunk in context_chunks
        )

    def answer_with_rag(
        self, question: str, context_chunks: List[Dict[str, Any]], topic: str = "Current lesson"
    ) -> str:
        if not context_chunks:
            raise ValueError("No indexed evidence was found for this question.")
        return self._chat(
            "You are a grounded course assistant. Always answer in clear English. Use only the supplied evidence. "
            "Cite every factual claim with chunk IDs in square brackets. If evidence is "
            "insufficient, say so explicitly and do not use outside knowledge.",
            f"Topic: {topic}\nQuestion: {question}\n\nEvidence:\n{self._context(context_chunks)}",
        )

    def summarize_with_rag(
        self, topic: str, context_chunks: List[Dict[str, Any]]
    ) -> str:
        if not context_chunks:
            raise ValueError("No page or video evidence was found to summarize.")
        return self._chat(
            "You are a patient English-speaking tutor. Teach only from the supplied evidence. "
            "Start with a concise plain-English summary, then explain the key ideas in a short "
            "structured lesson. Mention uncertainty or missing context instead of inventing facts. "
            "Cite factual claims with chunk IDs in square brackets.",
            f"Teach me this page or video.\nTopic: {topic}\n\nEvidence:\n{self._context(context_chunks)}",
        )

    def generate_quiz_with_rag(
        self,
        topic: str,
        context_chunks: List[Dict[str, Any]],
        mastery_score: float,
        difficulty: float,
        count: int = 3,
    ) -> List[Dict[str, Any]]:
        if not context_chunks:
            raise ValueError(
                f"No indexed evidence exists for '{topic}'. Add lesson text before generating a quiz."
            )
        schema = QuizPayload.model_json_schema()
        valid_ids = [chunk["chunk_id"] for chunk in context_chunks]
        prompt = (
            f"Create exactly {count} rigorous multiple-choice questions in English about {topic}. "
            f"Learner mastery is {mastery_score:.1f}/100 and target difficulty is {difficulty:.2f}. "
            "Every question, choice, and explanation must be written only in English and must be "
            "answerable only from the evidence. Test specific ideas actually stated in the evidence; "
            "never create generic questions from the title alone. Use four plausible, "
            "distinct choices. The answer must exactly equal one choice. Include one or more "
            f"citation IDs chosen only from this list: {valid_ids}. Vary Bloom levels appropriately.\n\n"
            f"Evidence:\n{self._context(context_chunks)}\n\n"
            f"Return JSON matching this schema: {json.dumps(schema)}"
        )
        raw = self._chat(
            "You are an English-language assessment designer. Never invent facts or citations. "
            "Do not output Hindi or Devanagari text. Return only schema-valid JSON.",
            prompt,
            schema=schema,
        )
        if re.search(r"[\u0900-\u097f]", raw):
            raw = self._chat(
                "You are an English-language assessment designer. Output English only. "
                "Do not use Hindi, Devanagari, invented facts, or invented citations. "
                "Return only schema-valid JSON.",
                prompt,
                schema=schema,
            )
        try:
            parsed = QuizPayload.model_validate_json(raw)
        except ValidationError as exc:
            raise LLMConfigurationError(f"The model returned an invalid quiz schema: {exc}") from exc
        questions = parsed.questions[:count]
        if len(questions) != count:
            raise LLMConfigurationError(
                f"The model generated {len(questions)} questions; {count} were required."
            )
        allowed = set(valid_ids)
        for question in questions:
            if not set(question.citations).issubset(allowed):
                raise LLMConfigurationError("The model invented a citation outside retrieved evidence.")
        return [question.model_dump() for question in questions]


llm_service = LLMService()
