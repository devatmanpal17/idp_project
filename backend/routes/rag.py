"""Persistent RAG ingestion, retrieval, grounded generation, and quiz evaluation."""

from __future__ import annotations

import time
import re
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

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
from ml.scheduler import controller
from ml.evidence_snapshot import snapshot, validate
from ml.publication import record, record_cached


def interactive_request():
    rag_engine.leases.expire()
    with controller.interactive_work():
        yield


router = APIRouter(dependencies=[Depends(interactive_request)])


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


def _generation_configuration():
    return llm_service.model, llm_service.configuration_version


def _validate_generation(chunks, evidence, configuration):
    validate(rag_engine, chunks, evidence)
    if _generation_configuration() != configuration:
        raise ValueError('AI model configuration changed during generation; retry.')
    record(rag_engine, chunks, evidence)


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
        configuration = _generation_configuration()
        active_document_id = req.document_id
        answer_key = None
        if req.source_type == 'video':
            if req.learner_key and req.video_key:
                active_document_id = None
            elif not active_document_id:
                raise ValueError('Video questions require an observation-tracked document.')
            if active_document_id:
                rag_engine.vectors.document(active_document_id)
            cache_scope = (f'scoped:{req.learner_key}|{req.video_key}'
                           if req.learner_key and req.video_key else active_document_id)
            with rag_engine._lock:
                if cache_scope and not req.history and not rag_engine.leases.has_open(cache_scope):
                    answer_key = rag_engine.answer_cache.key(
                        req.question, cache_scope, llm_service.model, req.top_k, req.topic)
                    cached_answer = rag_engine.answer_cache.get(answer_key, cache_scope)
                    if cached_answer is not None:
                        record_cached(rag_engine, answer_key, cache_scope)
                        return cached_answer
        if req.transcript_context and req.source_type != 'video':
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
        with rag_engine._lock:
            chunks = rag_engine.retrieve(
                req.question, topic=req.topic, top_k=req.top_k,
                document_id=active_document_id,
                learner_key=req.learner_key if req.source_type == 'video' else None,
                video_key=req.video_key if req.source_type == 'video' else None,
            )
            evidence = snapshot(rag_engine, chunks)
        answer = llm_service.answer_with_rag(
            req.question,
            chunks,
            req.topic or "Current lesson",
            history=[turn.model_dump() for turn in req.history],
        )
        with rag_engine._lock:
            _validate_generation(chunks, evidence, configuration)
            if req.source_type == 'video' and active_document_id and rag_engine.leases.would_hide(
                req.question, active_document_id, req.top_k, req.topic
            ):
                answer += '\n\nSome lecture material is locked until the quiz is submitted.'
            if req.source_type == 'video' and req.learner_key and req.video_key and rag_engine.leases.would_hide_scoped(
                req.question, req.learner_key, req.video_key, req.top_k, req.topic
            ):
                answer += '\n\nSome lecture material is locked until the quiz is submitted.'
            cited_sources = [
                chunk for chunk in chunks if f"[{chunk['chunk_id']}]" in answer
            ]
            response = {
                "answer": answer,
                "active_provider": llm_service._last_provider_used,
                "sources": cited_sources,
            }
            if answer_key is not None:
                import json
                vector_key = json.dumps([rag_engine.model_version,
                    ' '.join(f'{req.topic or ""} {req.question}'.split())])
                query_vector = rag_engine.query_vector_cache.get(vector_key)
                if query_vector is not None:
                    rag_engine.answer_cache.put(answer_key, cache_scope,
                        query_vector, req.top_k, chunks, response)
            return response
    except Exception as exc:
        raise _service_error(exc) from exc


@router.post("/api/rag/summarize")
def summarize_page(req: SummarizeRequest) -> Dict[str, Any]:
    try:
        configuration = _generation_configuration()
        if req.source_type == 'video':
            if req.learner_key and req.video_key:
                scope = {'learner_key': req.learner_key, 'video_key': req.video_key}
            else:
                if not req.document_id:
                    raise ValueError('Video summaries require an observation-tracked document.')
                rag_engine.vectors.document(req.document_id)
                scope = {'document_id': req.document_id}
            with rag_engine._lock:
                chunks = rag_engine.retrieve('main ideas explanation summary', top_k=10, **scope)
                evidence = snapshot(rag_engine, chunks)
            summary = llm_service.summarize_with_rag(req.topic, chunks)
            with rag_engine._lock:
                _validate_generation(chunks, evidence, configuration)
                return {'summary': summary, 'active_provider': llm_service._last_provider_used,
                        'sources': chunks}
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
        with rag_engine._lock:
            chunks = rag_engine.retrieve(
                "main ideas explanation summary", topic=req.topic, top_k=10,
                document_id=indexed["document_id"],
            )
            evidence = snapshot(rag_engine, chunks)
        summary = llm_service.summarize_with_rag(req.topic, chunks)
        with rag_engine._lock:
            _validate_generation(chunks, evidence, configuration)
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
        chunks = rag_engine.retrieve(req.query, topic=req.topic, top_k=req.top_k, document_id=req.document_id)
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
        configuration = _generation_configuration()
        active_document_id = req.document_id
        if req.source_type == 'video':
            if req.learner_key and req.video_key:
                active_document_id = None
            elif not active_document_id:
                _require_source_words(req.source_context or '', 'video', max(50, req.question_count * 15))
                raise ValueError('Video quizzes require an observation-tracked document.')
            if active_document_id:
                rag_engine.vectors.document(active_document_id)
        if req.source_context and req.source_type != 'video':
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
            learner_key=req.learner_key if req.source_type == 'video' else None,
            video_key=req.video_key if req.source_type == 'video' else None,
        )
        if not chunks:
            raise ValueError(
                f"No indexed lesson content exists for '{req.topic}'. Add source text first."
            )
        if req.source_type == 'video':
            _require_source_words(' '.join(chunk['snippet'] for chunk in chunks), 'video', max(50, req.question_count * 15))
        with rag_engine._lock:
            evidence = snapshot(rag_engine, chunks)
        calibration = calibrate_difficulty(
            mastery_score=req.mastery_score,
            error_count=len(req.recent_errors or []),
            question_count=req.question_count,
        )
        questions = llm_service.generate_quiz_with_rag(
            topic=req.topic,
            context_chunks=chunks,
            mastery_score=req.mastery_score,
            difficulty=calibration["difficulty"],
            count=req.question_count,
        )
        with rag_engine._lock:
            _validate_generation(chunks, evidence, configuration)
            quiz_id = quiz_analytics.save_quiz(req.topic, questions)
            if req.source_type == 'video':
                if req.learner_key and req.video_key:
                    rag_engine.leases.open_scoped(quiz_id, req.learner_key, req.video_key, questions)
                else:
                    rag_engine.leases.open(quiz_id, active_document_id, questions)
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
            "label": "Heuristic difficulty selection",
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
    rag_engine.leases.close(req.quiz_id)
    # Assessment outcomes change recall-based cache admission priorities.
    rag_engine.invalidate_cache()
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
    raise HTTPException(status_code=422, detail='Legacy timestamp-only capture is disabled. Use /api/vectors/transcript and /api/observation/intervals.')


@router.post('/api/rag/abandon-quiz/{quiz_id}')
def abandon_quiz(quiz_id: str) -> Dict[str, Any]:
    return {'restored_chunks': rag_engine.leases.close(quiz_id)}
