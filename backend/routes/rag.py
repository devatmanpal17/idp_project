"""Persistent RAG ingestion, retrieval, grounded generation, and quiz evaluation."""

from __future__ import annotations

import time
import re
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from ..models import (
    AskRequest,
    EvaluateQuizRequest,
    GenerateQuizRequest,
    IngestDocumentRequest,
    RetrieveRequest,
    StreamTranscriptRequest,
    SummarizeRequest,
)
from ml import (
    calibrate_difficulty,
    compute_mastery_update,
    generate_concept_graph,
    generate_irt_curve,
    generate_mastery_shift_chart,
    generate_similarity_distribution_chart,
    llm_service,
    rag_engine,
)
from ml.analytics import quiz_analytics
from ml.llm_service import LLMConfigurationError
from ml.rag_engine import RAGConfigurationError

router = APIRouter()


def _require_source_words(text: str, source_type: str, minimum: int) -> None:
    countable_text = re.sub(r"^\[[^\]]+\]\s*", "", text, flags=re.MULTILINE) if source_type == "video" else text
    word_count = len(countable_text.split())
    if source_type == "video" and word_count < minimum:
        raise ValueError(
            f"Only {word_count} caption words were captured from this video. "
            "Turn on English captions and watch a little more before trying again."
        )
    if source_type == "document" and word_count < 20:
        raise ValueError("The active document does not contain enough readable text.")


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (RAGConfigurationError, LLMConfigurationError)):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="The AI pipeline failed unexpectedly.")


@router.get("/api/rag/topics")
def indexed_topics() -> Dict[str, Any]:
    return {"topics": rag_engine.topics(), "indexed_chunks": rag_engine.count}


@router.post("/api/rag/ingest")
def ingest_document(req: IngestDocumentRequest) -> Dict[str, Any]:
    try:
        result = rag_engine.ingest_document(
            text=req.content,
            topic=req.topic,
            source=req.title,
            course=req.course,
        )
        return {"status": "indexed", "topic": req.topic, **result}
    except Exception as exc:
        raise _service_error(exc) from exc


@router.post("/api/rag/ask")
def ask_lesson(req: AskRequest) -> Dict[str, Any]:
    try:
        active_document_id = None
        if req.transcript_context:
            _require_source_words(req.transcript_context, req.source_type, 8)
            indexed = rag_engine.ingest_transcript(
                text=req.transcript_context,
                topic=req.topic or "Current lesson",
                course="Question context",
                timestamp="current",
                extra_metadata={
                    "source_type": req.source_type,
                    "observed_until_seconds": req.observed_until_seconds,
                },
            )
            active_document_id = indexed["document_id"]
        chunks = rag_engine.retrieve(
            req.question, topic=req.topic, top_k=req.top_k,
            document_id=active_document_id,
        )
        answer = llm_service.answer_with_rag(
            req.question,
            chunks,
            req.topic or "Current lesson",
            history=[turn.model_dump() for turn in req.history],
        )
        cited_sources = [
            chunk for chunk in chunks if f"[{chunk['chunk_id']}]" in answer
        ]
        return {
            "answer": answer,
            "active_provider": llm_service._last_provider_used,
            "sources": cited_sources,
        }
    except Exception as exc:
        raise _service_error(exc) from exc


@router.post("/api/rag/summarize")
def summarize_page(req: SummarizeRequest) -> Dict[str, Any]:
    try:
        _require_source_words(req.page_content, req.source_type, 20)
        indexed = rag_engine.ingest_document(
            text=req.page_content,
            topic=req.topic,
            source=f"Page: {req.topic}",
            course=req.topic,
            extra_metadata={
                "page_url": req.page_url or "",
                "capture_type": "page",
                "source_type": req.source_type,
                "observed_until_seconds": req.observed_until_seconds,
            },
        )
        chunks = rag_engine.retrieve(
            "main ideas explanation summary", topic=req.topic, top_k=10,
            document_id=indexed["document_id"],
        )
        summary = llm_service.summarize_with_rag(req.topic, chunks)
        return {
            "summary": summary,
            "active_provider": llm_service._last_provider_used,
            "sources": chunks,
        }
    except Exception as exc:
        raise _service_error(exc) from exc


@router.post("/api/rag/retrieve")
def retrieve_chunks(req: RetrieveRequest) -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        chunks = rag_engine.retrieve(req.query, topic=req.topic, top_k=req.top_k)
    except Exception as exc:
        raise _service_error(exc) from exc
    return {
        "topic": req.topic,
        "query": req.query,
        "chunks_found": len(chunks),
        "retrieval_time_ms": round((time.perf_counter() - start) * 1000, 2),
        "vector_database": "chromadb",
        "embedding_model": rag_engine.embeddings.model,
        "chunks": chunks,
    }


@router.post("/api/rag/generate-quiz")
def generate_quiz(req: GenerateQuizRequest) -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        active_document_id = None
        if req.source_context:
            _require_source_words(
                req.source_context, req.source_type, max(50, req.question_count * 15)
            )
            indexed = rag_engine.ingest_document(
                text=req.source_context,
                topic=req.topic,
                source=f"Active page: {req.topic}",
                course=req.topic,
                extra_metadata={
                    "page_url": req.page_url or "",
                    "capture_type": "quiz_context",
                    "source_type": req.source_type,
                    "observed_until_seconds": req.observed_until_seconds,
                },
            )
            active_document_id = indexed["document_id"]
        chunks = rag_engine.retrieve(
            req.topic, topic=req.topic, top_k=8, document_id=active_document_id,
            require_topic=active_document_id is None,
        )
        if not chunks:
            raise ValueError(
                f"No indexed lesson content exists for '{req.topic}'. Add source text first."
            )
        calibration = calibrate_difficulty(
            mastery_score=req.mastery_score,
            error_count=len(req.recent_errors or []),
        )
        questions = llm_service.generate_quiz_with_rag(
            topic=req.topic,
            context_chunks=chunks,
            mastery_score=req.mastery_score,
            difficulty=calibration["difficulty"],
            count=req.question_count,
        )
        quiz_id = quiz_analytics.save_quiz(req.topic, questions)
    except Exception as exc:
        raise _service_error(exc) from exc

    bloom_counts: Dict[str, int] = {}
    for question in questions:
        level = question["bloom_level"]
        bloom_counts[level] = bloom_counts.get(level, 0) + 1
    cognitive_dimensions = [
        {
            "dimension": level,
            "weight": round(count / len(questions) * 100, 1),
            "target": round(count / len(questions) * 100, 1),
        }
        for level, count in bloom_counts.items()
    ]
    public_questions = [
        {
            "question_id": f"{quiz_id}_{index}",
            "q": question["q"],
            "choices": question["choices"],
            "citations": question["citations"],
            "bloom_level": question["bloom_level"],
        }
        for index, question in enumerate(questions)
    ]
    elapsed = round((time.perf_counter() - start) * 1000, 2)
    telemetry_steps = [
        {
            "step": "retrieve",
            "label": "ChromaDB semantic retrieval",
            "detail": f"{len(chunks)} cosine-ranked chunks",
            "lines": [
                f"{chunk['chunk_id']}  cosine={chunk['similarity']:.4f}  {chunk['source']}"
                for chunk in chunks[:4]
            ],
        },
        {
            "step": "signals",
            "label": "Learner signal calibration",
            "detail": f"mastery={req.mastery_score:.1f}",
            "lines": [
                f"quiz performance = {req.quiz_perf_pct or 0:.1f}",
                f"time on section = {req.time_on_section_pct or 0:.1f}",
                f"recent errors = {len(req.recent_errors or [])}",
            ],
        },
        {
            "step": "calibrate",
            "label": "IRT difficulty calibration",
            "detail": calibration["target_level"],
            "lines": [calibration["formula"], f"target success = {calibration['target_success_rate']}"],
        },
        {
            "step": "generate",
            "label": "Grounded structured generation",
            "detail": llm_service.active_provider,
            "lines": [
                f"schema validated = true",
                f"citation allow-list = {len(chunks)} chunks",
                f"quiz session = {quiz_id[:12]}",
            ],
        },
    ]
    return {
        "quiz_id": quiz_id,
        "topic": req.topic,
        "mastery_score": req.mastery_score,
        "active_provider": llm_service.active_provider,
        "calibration": calibration,
        "telemetry_steps": telemetry_steps,
        "questions": public_questions,
        "graphs": {
            "similarity_chart": generate_similarity_distribution_chart(chunks),
            "irt_curve": generate_irt_curve(calibration["difficulty"], req.mastery_score),
            "cognitive_dimensions": cognitive_dimensions,
            "concept_graph": generate_concept_graph(req.topic, chunks),
        },
        "total_time_ms": elapsed,
    }


@router.post("/api/rag/evaluate-quiz")
def evaluate_quiz(req: EvaluateQuizRequest) -> Dict[str, Any]:
    stored = quiz_analytics.get_quiz(req.quiz_id)
    if not stored:
        raise HTTPException(status_code=404, detail="Quiz session was not found.")
    questions: List[Dict[str, Any]] = stored["questions"]
    if len(req.given_answers) != len(questions):
        raise HTTPException(status_code=422, detail="Answer count does not match the quiz.")
    evaluations: List[Dict[str, Any]] = []
    correct_count = 0
    for question, given in zip(questions, req.given_answers):
        correct = given.strip().casefold() == question["answer"].strip().casefold()
        correct_count += int(correct)
        evaluations.append(
            {
                "question": question["q"],
                "given_answer": given,
                "expected_answer": question["answer"],
                "is_correct": correct,
                "explanation": question["why"],
                "citations": question["citations"],
                "bloom_level": question["bloom_level"],
            }
        )
    score = round(correct_count / max(1, len(questions)) * 100, 1)
    mastery = compute_mastery_update(score, req.current_mastery)
    attempt_id = quiz_analytics.record(
        topic=stored["topic"],
        score=score,
        previous_mastery=req.current_mastery,
        new_mastery=mastery["new_mastery"],
        correct_count=correct_count,
        question_count=len(questions),
        details=evaluations,
    )
    return {
        "attempt_id": attempt_id,
        "score": score,
        "correct_count": correct_count,
        "total_questions": len(questions),
        "evaluations": evaluations,
        "previous_mastery": req.current_mastery,
        "new_mastery": mastery["new_mastery"],
        "mastery_delta": mastery["mastery_delta"],
        "feedback_summary": (
            "Strong result. Continue with a higher difficulty."
            if score >= 80
            else "Review the cited evidence for missed questions and retry."
            if score >= 50
            else "Revisit the retrieved lesson sections before another attempt."
        ),
        "mastery_shift_chart": generate_mastery_shift_chart(
            req.current_mastery, mastery["new_mastery"], score
        ),
        "mastery_history": quiz_analytics.history(stored["topic"]),
    }


@router.post("/api/rag/stream-transcript")
def stream_transcript(req: StreamTranscriptRequest) -> Dict[str, Any]:
    try:
        indexed = rag_engine.ingest_transcript(
            req.transcript_segment,
            req.current_topic,
            req.video_title,
            req.timestamp,
            extra_metadata={
                "page_url": req.page_url or "",
                "dwell_seconds": req.dwell_seconds,
                "video_position_seconds": req.video_position_seconds or 0,
                "video_duration_seconds": req.video_duration_seconds or 0,
            },
        )
    except Exception as exc:
        raise _service_error(exc) from exc
    word_count = len(req.transcript_segment.split())
    comprehension_factor = min(1.0, req.dwell_seconds / max(1, word_count * 0.3))
    return {
        "video": req.video_title,
        "timestamp": req.timestamp,
        "words_captured": word_count,
        "live_signal_delta": round((comprehension_factor - 0.5) * 2.0, 1),
        "status": "indexed_to_chromadb",
        **indexed,
    }
