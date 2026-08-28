"""Recommendations derived from persisted assessment evidence."""

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter

from ml.analytics import quiz_analytics

router = APIRouter()


@router.get("/api/recommendations/smart")
def get_smart_recommendations() -> Dict[str, Any]:
    recommendations = []
    now = datetime.now(timezone.utc)
    for index, summary in enumerate(quiz_analytics.topic_summaries()):
        mastery = float(summary["current_mastery"])
        average = float(summary["average_score"])
        last_attempt = datetime.fromisoformat(summary["last_attempt_at"])
        days_since = max(0, (now - last_attempt).days)
        weakness = 100.0 - mastery
        recency_pressure = min(25.0, days_since * 2.5)
        impact = round(min(100.0, weakness * 0.7 + (100.0 - average) * 0.2 + recency_pressure), 1)
        action = "Generate reinforcement quiz" if mastery < 70 else "Run retention check"
        recommendations.append(
            {
                "id": f"rec_{index + 1}",
                "topic": summary["topic"],
                "course": "Indexed lesson collection",
                "type": "revisit_weak_topic" if mastery < 70 else "retention_check",
                "impact_score": impact,
                "estimated_minutes": max(10, min(40, round(10 + weakness / 4))),
                "reasoning": (
                    f"Based on {summary['attempts']} persisted attempt(s): mastery is "
                    f"{mastery:.1f}, average quiz score is {average:.1f}, and the latest "
                    f"mastery change is {summary['mastery_trend']:+.1f}."
                ),
                "action": action,
            }
        )
    recommendations.sort(key=lambda item: item["impact_score"], reverse=True)
    return {"recommendations": recommendations}
