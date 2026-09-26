"""
ChaiGaram ML — Learner Signal Difficulty Calibration
Heuristic difficulty from mastery/errors and a fixed-rate mastery update.
"""

from typing import Dict, Any


def calibrate_difficulty(mastery_score: float, error_count: int = 0, question_count: int = 4) -> Dict[str, Any]:
    """
    Calculates adaptive difficulty and question mix based on learner signals.
    Formula: clamp(mastery/100 + 0.15 - error_penalty, 0.25, 0.85)
    """
    error_penalty = min(0.15, error_count * 0.03)
    raw_diff = (mastery_score / 100.0) + 0.15 - error_penalty
    difficulty = max(0.25, min(0.85, raw_diff))

    # Determine question mix based on difficulty thresholds
    if difficulty >= 0.70:
        target_level = "Advanced Application & Synthesis"
    elif difficulty >= 0.50:
        target_level = "Intermediate Comprehension"
    else:
        target_level = "Foundational Recall & Reinforcement"

    return {
        "difficulty": round(difficulty, 2),
        "target_success_rate": 0.70,
        "target_level": target_level,
        "mix": {"mcq": question_count, "short_answer": 0},
        "method": "mastery_error_heuristic",
        "formula": f"clamp(mastery/100 + 0.15 - {error_penalty:.2f}, 0.25, 0.85) -> {difficulty:.2f}"
    }


def compute_mastery_update(score_pct: float, current_mastery: float) -> Dict[str, Any]:
    """
    Fixed-rate mastery score updater, not a fitted Bayesian model.
    Adjusts learner mastery proportionally based on test score delta.
    """
    mastery_delta = round((score_pct - current_mastery) * 0.22, 1)
    new_mastery = max(0.0, min(100.0, round(current_mastery + mastery_delta, 1)))
    return {
        "previous_mastery": current_mastery,
        "new_mastery": new_mastery,
        "mastery_delta": mastery_delta,
    }
