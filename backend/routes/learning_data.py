"""Live product data derived from Chroma evidence and persisted quiz attempts."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import APIRouter, HTTPException, Path, Query

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


def _canonical_url(value: str) -> str:
    """Keep source identity stable while discarding tracking and page fragments."""
    raw = value.strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        query_items = parse_qsl(parsed.query, keep_blank_values=False)
        if "youtube.com" in parsed.netloc.lower() and parsed.path == "/watch":
            query_items = [(key, val) for key, val in query_items if key == "v"]
        else:
            query_items = [
                (key, val)
                for key, val in query_items
                if not key.lower().startswith("utm_")
                and key.lower() not in {"fbclid", "gclid", "ref", "source"}
            ]
        return urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path or "/",
                "",
                urlencode(query_items),
                "",
            )
        )
    except ValueError:
        return ""


def _document_catalogue(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    by_document: Dict[str, Dict[str, Any]] = {}
    for record in records:
        document_id = str(record.get("document_id") or record["chunk_id"])
        existing = by_document.setdefault(document_id, dict(record))
        existing["document_id"] = document_id
        existing["chunk_count"] = int(existing.get("chunk_count", 0)) + 1
        existing["word_count"] = int(existing.get("word_count", 0)) + len(
            str(record.get("text") or "").split()
        )
    return by_document


def _history_groups(
    documents: Dict[str, Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for document in documents.values():
        page_url = _canonical_url(str(document.get("page_url") or ""))
        # Question-only working copies are temporary retrieval context, not visits.
        if not page_url and str(document.get("course") or "") == "Question context":
            continue
        key = f"url:{page_url}" if page_url else f"document:{document['document_id']}"
        groups[_id("history", key)].append({**document, "canonical_page_url": page_url})
    return groups


def _history_entries(documents: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for history_id, grouped in _history_groups(documents).items():
        ordered = sorted(grouped, key=lambda item: str(item.get("ingested_at") or ""))
        latest = ordered[-1]
        page_url = str(latest.get("canonical_page_url") or "")
        topics = sorted(
            {str(item.get("topic") or "Uncategorised") for item in grouped}
        )
        progress_values = [
            min(
                100.0,
                float(item.get("video_position_seconds") or 0)
                / float(item.get("video_duration_seconds") or 1)
                * 100,
            )
            for item in grouped
            if float(item.get("video_duration_seconds") or 0) > 0
        ]
        title = str(
            latest.get("course")
            or latest.get("topic")
            or latest.get("source")
            or "Saved learning source"
        )
        entries.append(
            {
                "id": history_id,
                "title": title,
                "topics": topics,
                "page_url": page_url,
                "domain": urlparse(page_url).hostname or "Local document",
                "platform": _platform(page_url),
                "source_type": (
                    "video"
                    if any(str(item.get("source_type") or "") == "video" for item in grouped)
                    or any(float(item.get("video_duration_seconds") or 0) > 0 for item in grouped)
                    else "document"
                ),
                "first_visited_at": str(ordered[0].get("ingested_at") or ""),
                "last_visited_at": str(latest.get("ingested_at") or ""),
                "visit_count": len(grouped),
                "indexed_chunks": sum(int(item.get("chunk_count", 0)) for item in grouped),
                "word_count": sum(int(item.get("word_count", 0)) for item in grouped),
                "progress_pct": round(max(progress_values), 1) if progress_values else 0,
                "document_ids": [str(item["document_id"]) for item in grouped],
            }
        )
    entries.sort(key=lambda item: item["last_visited_at"], reverse=True)
    return entries


def build_learning_data() -> Dict[str, Any]:
    records = rag_engine.catalogue_records()
    attempts = quiz_analytics.attempts()
    summaries = {item["topic"]: item for item in quiz_analytics.topic_summaries()}

    by_document = _document_catalogue(records)

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
        quiz_perf_pct = float(summary.get("average_score", 0))
        time_on_section_pct = round(min(100.0, dwell_seconds / 900 * 100), 1)
        revisit_frequency_pct = round(min(100.0, len(documents) / 5 * 100), 1)
        mastery_score = round(
            quiz_perf_pct * 0.4
            + time_on_section_pct * 0.35
            + revisit_frequency_pct * 0.25,
            1,
        )
        topics.append(
            {
                "id": topic_id,
                "course_id": course_ids[course],
                "title": topic,
                "mastery_score": mastery_score,
                "assessment_mastery": float(summary.get("current_mastery", 0)),
                "quiz_perf_pct": quiz_perf_pct,
                "time_on_section_pct": time_on_section_pct,
                "revisit_frequency_pct": revisit_frequency_pct,
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
        course_mastery = [
            float(item["mastery_score"])
            for item in topics
            if item["course_id"] == course_ids[course]
            and item["title"] in course_topic_names
        ]
        progress_values = [
            min(100.0, float(item.get("video_position_seconds") or 0) / float(item.get("video_duration_seconds") or 1) * 100)
            for item in documents
            if float(item.get("video_duration_seconds") or 0) > 0
        ]
        ordered_documents = sorted(
            documents,
            key=lambda item: str(item.get("ingested_at") or ""),
            reverse=True,
        )
        page_url = next(
            (
                _canonical_url(str(item.get("page_url") or ""))
                for item in ordered_documents
                if item.get("page_url")
            ),
            "",
        )
        last_visited_at = max(
            (str(item.get("ingested_at") or "") for item in documents),
            default="",
        )
        courses.append(
            {
                "id": course_ids[course],
                "title": course,
                "platform": _platform(page_url),
                "thumbnail_url": None,
                "source_url": page_url,
                "last_visited_at": last_visited_at,
                "visit_count": len(documents),
                "completion_pct": round(max(progress_values), 1) if progress_values else 0,
                "overall_mastery": round(sum(course_mastery) / len(course_mastery), 1)
                if course_mastery
                else 0,
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
    for index, topic_item in enumerate(topics):
        summary = summaries.get(topic_item["title"])
        if summary:
            mastery = float(topic_item["mastery_score"])
            average = float(summary["average_score"])
            last_attempt = datetime.fromisoformat(summary["last_attempt_at"])
            days_since = max(0, (now - last_attempt).days)
            impact = round(
                min(
                    100,
                    (100 - mastery) * 0.7
                    + (100 - average) * 0.2
                    + min(25, days_since * 2.5),
                ),
                1,
            )
            recommendation_type = (
                "revisit_weak_topic" if mastery < 70 else "retention_check"
            )
            reasoning = (
                f"Calculated from {summary['attempts']} attempt(s): mastery {mastery:.1f}, "
                f"average score {average:.1f}, trend {summary['mastery_trend']:+.1f}."
            )
            created_at = summary["last_attempt_at"]
        else:
            mastery = float(topic_item["mastery_score"])
            impact = round(
                min(
                    100,
                    60
                    + float(topic_item["revisit_frequency_pct"]) * 0.15
                    + float(topic_item["time_on_section_pct"]) * 0.1,
                ),
                1,
            )
            recommendation_type = "initial_assessment"
            reasoning = (
                f"This source has {topic_item['indexed_chunks']} indexed passage(s) and "
                f"{topic_item['minutes_on_section']:.1f} tracked minute(s), but no completed "
                "assessment yet. Start with a short baseline quiz."
            )
            created_at = topic_item["last_updated"]
        recommendations.append(
            {
                "id": f"rec_{index + 1}",
                "topic_id": topic_item["id"],
                "type": recommendation_type,
                "impact_score": impact,
                "estimated_minutes": max(
                    8, min(40, round(8 + (100 - mastery) / 5))
                ),
                "reasoning": reasoning,
                "created_at": created_at,
            }
        )
    recommendations.sort(key=lambda item: item["impact_score"], reverse=True)

    study_events = []
    first_slot = datetime.combine(now.date(), time(hour=18), tzinfo=timezone.utc)
    if first_slot <= now:
        first_slot += timedelta(days=1)
    for topic_item in topics:
        mastery = float(topic_item["mastery_score"])
        if not topic_item["assessed"]:
            event_pattern = [(0, "quiz"), (2, "review"), (5, "study_block")]
        elif mastery < 50:
            event_pattern = [(1, "review"), (3, "quiz"), (7, "review")]
        elif mastery < 75:
            event_pattern = [(2, "review"), (7, "quiz"), (14, "review")]
        else:
            event_pattern = [(4, "review"), (14, "quiz"), (30, "review")]
        for offset_days, event_type in event_pattern:
            scheduled_at = first_slot + timedelta(days=offset_days)
            study_events.append(
                {
                    "id": _id(
                        "event",
                        f"{topic_item['id']}|{event_type}|{scheduled_at.date().isoformat()}",
                    ),
                    "topic_id": topic_item["id"],
                    "event_type": event_type,
                    "scheduled_at": scheduled_at.isoformat(),
                    "status": "scheduled",
                }
            )
    study_events.sort(key=lambda item: item["scheduled_at"])

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
        "study_events": study_events,
        "recommendations": recommendations,
        "activity_log": activities,
        "history": [
            {key: value for key, value in entry.items() if key != "document_ids"}
            for entry in _history_entries(by_document)
        ],
    }


@router.get("/api/learning/data")
def learning_data() -> Dict[str, Any]:
    return build_learning_data()


@router.delete("/api/learning/history/{history_id}")
def delete_history_entry(
    history_id: str = Path(..., pattern=r"^history_[a-f0-9]{16}$"),
) -> Dict[str, Any]:
    documents = _document_catalogue(rag_engine.catalogue_records())
    entry = next(
        (
            item
            for item in _history_entries(documents)
            if item["id"] == history_id
        ),
        None,
    )
    if not entry:
        raise HTTPException(status_code=404, detail="History entry was not found.")

    affected_topics = set(entry["topics"])
    removed_chunks = rag_engine.delete_documents(entry["document_ids"])
    remaining_topics = set(rag_engine.topics())
    orphaned_topics = sorted(affected_topics - remaining_topics)
    removed_assessments = quiz_analytics.delete_topics(orphaned_topics)
    return {
        "status": "deleted",
        "history_id": history_id,
        "removed_documents": len(entry["document_ids"]),
        "removed_chunks": removed_chunks,
        "removed_topics": orphaned_topics,
        "removed_assessments": removed_assessments,
    }


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
