"""Live product data derived from Chroma evidence and persisted quiz attempts."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import urlparse

from fastapi import APIRouter, Query

from ml import rag_engine
from ml.analytics import quiz_analytics

router = APIRouter()


def _id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _platform(url: str) -> str:
    host = urlparse(url).hostname or ""
    if "coursera" in host:
        return "Coursera"
    if "udemy" in host:
        return "Udemy"
    if "edx" in host:
        return "edX"
    if "youtube" in host or "youtu.be" in host:
        return "YouTube"
    return "Web" if host else "Document"


def build_learning_data() -> Dict[str, Any]:
    records = rag_engine.catalogue_records()
    attempts = quiz_analytics.attempts()
    summaries = {item["topic"]: item for item in quiz_analytics.topic_summaries()}

    by_document: Dict[str, Dict[str, Any]] = {}
    for record in records:
        document_id = str(record.get("document_id") or record["chunk_id"])
        existing = by_document.setdefault(document_id, dict(record))
        existing["chunk_count"] = int(existing.get("chunk_count", 0)) + 1
        existing["word_count"] = int(existing.get("word_count", 0)) + len(record["text"].split())

    topic_documents: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    course_documents: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for document in by_document.values():
        topic = str(document.get("topic") or "Uncategorised")
        course = str(document.get("course") or document.get("source") or "Indexed material")
        document["resolved_course"] = course
        topic_documents[topic].append(document)
        course_documents[course].append(document)

    topics: List[Dict[str, Any]] = []
    topic_ids: Dict[str, str] = {}
    course_ids = {course: _id("course", course) for course in course_documents}
    for topic, documents in topic_documents.items():
        summary = summaries.get(topic, {})
        topic_id = _id("topic", topic)
        topic_ids[topic] = topic_id
        course = documents[-1]["resolved_course"]
        dwell_seconds = sum(float(item.get("dwell_seconds") or 0) for item in documents)
        topics.append(
            {
                "id": topic_id,
                "course_id": course_ids[course],
                "title": topic,
                "mastery_score": float(summary.get("current_mastery", 0)),
                "quiz_perf_pct": float(summary.get("average_score", 0)),
                "time_on_section_pct": 0,
                "revisit_frequency_pct": 0,
                "trend_delta": float(summary.get("mastery_trend", 0)),
                "minutes_on_section": round(dwell_seconds / 60, 1),
                "revisits": len(documents),
                "last_updated": max(
                    (str(item.get("ingested_at") or "") for item in documents),
                    default="",
                ),
                "indexed_chunks": sum(int(item.get("chunk_count", 0)) for item in documents),
                "assessed": bool(summary),
            }
        )

    courses: List[Dict[str, Any]] = []
    for course, documents in course_documents.items():
        course_topic_names = {str(item.get("topic") or "Uncategorised") for item in documents}
        assessed_mastery = [
            float(summaries[name]["current_mastery"])
            for name in course_topic_names
            if name in summaries
        ]
        progress_values = [
            min(100.0, float(item.get("video_position_seconds") or 0) / float(item.get("video_duration_seconds") or 1) * 100)
            for item in documents
            if float(item.get("video_duration_seconds") or 0) > 0
        ]
        page_url = next((str(item.get("page_url")) for item in documents if item.get("page_url")), "")
        courses.append(
            {
                "id": course_ids[course],
                "title": course,
                "platform": _platform(page_url),
                "thumbnail_url": None,
                "completion_pct": round(max(progress_values), 1) if progress_values else 0,
                "overall_mastery": round(sum(assessed_mastery) / len(assessed_mastery), 1) if assessed_mastery else 0,
                "created_at": min(
                    (str(item.get("ingested_at") or "") for item in documents),
                    default="",
                ),
            }
        )

    quizzes = []
    for attempt in attempts:
        topic = attempt["topic"]
        topic_documents_for_attempt = topic_documents.get(topic, [])
        course = topic_documents_for_attempt[-1]["resolved_course"] if topic_documents_for_attempt else ""
        quizzes.append(
            {
                "id": str(attempt["id"]),
                "topic_id": topic_ids.get(topic),
                "course_id": course_ids.get(course),
                "question_type": "llm_grounded_mcq",
                "questions": [
                    {
                        "q": item["question"],
                        "answer": item["expected_answer"],
                        "given": item["given_answer"],
                        "correct": item["is_correct"],
                        "explanation": item["explanation"],
                    }
                    for item in attempt["details"]
                ],
                "score": attempt["score"],
                "completed_at": attempt["completed_at"],
            }
        )

    recommendations = []
    now = datetime.now(timezone.utc)
    for index, summary in enumerate(summaries.values()):
        mastery = float(summary["current_mastery"])
        average = float(summary["average_score"])
        last_attempt = datetime.fromisoformat(summary["last_attempt_at"])
        days_since = max(0, (now - last_attempt).days)
        impact = round(min(100, (100 - mastery) * 0.7 + (100 - average) * 0.2 + min(25, days_since * 2.5)), 1)
        recommendations.append(
            {
                "id": f"rec_{index + 1}",
                "topic_id": topic_ids.get(summary["topic"]),
                "type": "revisit_weak_topic" if mastery < 70 else "retention_check",
                "impact_score": impact,
                "estimated_minutes": max(10, min(40, round(10 + (100 - mastery) / 4))),
                "reasoning": (
                    f"Calculated from {summary['attempts']} attempt(s): mastery {mastery:.1f}, "
                    f"average score {average:.1f}, trend {summary['mastery_trend']:+.1f}."
                ),
                "created_at": summary["last_attempt_at"],
            }
        )
    recommendations.sort(key=lambda item: item["impact_score"], reverse=True)

    activities = []
    for document in by_document.values():
        course = document["resolved_course"]
        activities.append(
            {
                "id": f"capture_{document.get('document_id')}",
                "course_id": course_ids.get(course),
                "event_type": "transcript_captured",
                "metadata": {
                    "topic": document.get("topic"),
                    "words": document.get("word_count", 0),
                },
                "created_at": document.get("ingested_at") or "",
            }
        )
    for attempt in attempts:
        topic = attempt["topic"]
        documents = topic_documents.get(topic, [])
        course = documents[-1]["resolved_course"] if documents else ""
        activities.append(
            {
                "id": f"quiz_{attempt['id']}",
                "course_id": course_ids.get(course),
                "event_type": "quiz_completed",
                "metadata": {
                    "topic": topic,
                    "score": attempt["score"],
                    "delta": round(attempt["new_mastery"] - attempt["previous_mastery"], 1),
                },
                "created_at": attempt["completed_at"],
            }
        )
    activities.sort(key=lambda item: item["created_at"], reverse=True)
    return {
        "courses": courses,
        "topics": topics,
        "quizzes": quizzes,
        "study_events": [],
        "recommendations": recommendations,
        "activity_log": activities,
    }


@router.get("/api/learning/data")
def learning_data() -> Dict[str, Any]:
    return build_learning_data()


@router.get("/api/learning/topic-state")
def topic_state(topic: str = Query(..., min_length=2, max_length=300)) -> Dict[str, Any]:
    data = build_learning_data()
    item = next((entry for entry in data["topics"] if entry["title"] == topic), None)
    if item:
        return item
    return {
        "id": _id("topic", topic),
        "title": topic,
        "mastery_score": 0,
        "quiz_perf_pct": 0,
        "trend_delta": 0,
        "minutes_on_section": 0,
        "revisits": 0,
        "indexed_chunks": 0,
        "assessed": False,
    }
