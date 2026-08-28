"""SQLite-backed quiz attempt store used by mastery and history graphs."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List


class QuizAnalyticsStore:
    def __init__(self) -> None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "analytics.sqlite3"
        self._lock = RLock()
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS quiz_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    score REAL NOT NULL,
                    previous_mastery REAL NOT NULL,
                    new_mastery REAL NOT NULL,
                    correct_count INTEGER NOT NULL,
                    question_count INTEGER NOT NULL,
                    details_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS generated_quizzes (
                    id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    questions_json TEXT NOT NULL
                )
                """
            )

    def save_quiz(self, topic: str, questions: List[Dict[str, Any]]) -> str:
        quiz_id = uuid.uuid4().hex
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO generated_quizzes VALUES (?, ?, ?, ?)",
                (
                    quiz_id,
                    topic,
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(questions),
                ),
            )
        return quiz_id

    def get_quiz(self, quiz_id: str) -> Dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT topic, questions_json FROM generated_quizzes WHERE id = ?",
                (quiz_id,),
            ).fetchone()
        if not row:
            return None
        return {"topic": row["topic"], "questions": json.loads(row["questions_json"])}

    def record(
        self,
        topic: str,
        score: float,
        previous_mastery: float,
        new_mastery: float,
        correct_count: int,
        question_count: int,
        details: List[Dict[str, Any]],
    ) -> int:
        completed_at = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO quiz_attempts (
                    topic, completed_at, score, previous_mastery, new_mastery,
                    correct_count, question_count, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    topic,
                    completed_at,
                    score,
                    previous_mastery,
                    new_mastery,
                    correct_count,
                    question_count,
                    json.dumps(details),
                ),
            )
            return int(cursor.lastrowid)

    def history(self, topic: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, completed_at, score, previous_mastery, new_mastery
                FROM quiz_attempts
                WHERE topic = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (topic, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def topic_summaries(self) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT topic, score, new_mastery, completed_at
                FROM quiz_attempts
                ORDER BY id ASC
                """
            ).fetchall()
        grouped: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            summary = grouped.setdefault(
                row["topic"],
                {"topic": row["topic"], "attempts": 0, "scores": [], "mastery_values": []},
            )
            summary["attempts"] += 1
            summary["scores"].append(float(row["score"]))
            summary["mastery_values"].append(float(row["new_mastery"]))
            summary["last_attempt_at"] = row["completed_at"]
        results = []
        for summary in grouped.values():
            mastery_values = summary.pop("mastery_values")
            scores = summary.pop("scores")
            summary["current_mastery"] = mastery_values[-1]
            summary["average_score"] = round(sum(scores) / len(scores), 1)
            summary["mastery_trend"] = round(
                mastery_values[-1] - mastery_values[-2], 1
            ) if len(mastery_values) > 1 else 0.0
            results.append(summary)
        return results

    def attempts(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, topic, completed_at, score, previous_mastery, new_mastery,
                       correct_count, question_count, details_json
                FROM quiz_attempts
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {**dict(row), "details": json.loads(row["details_json"])}
            for row in rows
        ]


quiz_analytics = QuizAnalyticsStore()
