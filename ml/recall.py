"""Regularized assessment-success model with an explicit cold-start heuristic.

Training pairs use only a topic's PREVIOUS score and elapsed time to predict its
next assessment score. This estimates assessment performance, not measured memory.
"""
import math
from datetime import datetime, timezone
import numpy as np


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (ValueError, TypeError):
        return None


class RecallModel:
    def __init__(self, attempts, minimum_pairs=20):
        self.weights = None
        self.latest = {}
        self.samples = []
        self.fit_brier = None
        rows = []
        for item in attempts:
            at = timestamp(item.get('completed_at'))
            try:
                score = float(item['score']) / 100
            except (KeyError, TypeError, ValueError):
                continue
            if at is not None and math.isfinite(score) and 0 <= score <= 1:
                rows.append((at, item['topic'], score))
        for at, topic, score in sorted(rows, key=lambda row: row[0]):
            previous = self.latest.get(topic)
            if previous and at > previous[0]:
                days = (at - previous[0]).total_seconds() / 86400
                self.samples.append(([1, previous[1], math.log1p(days)], score))
            self.latest[topic] = (at, score)
        if len(self.samples) >= minimum_pairs and len({y for _, y in self.samples}) > 1:
            x = np.array([x for x, _ in self.samples], dtype=float)
            y = np.array([y for _, y in self.samples], dtype=float)
            weights = np.array([0., 1., -.25])
            rate = .4 / max(1., float(np.mean(np.sum(x * x, axis=1))))
            for _ in range(800):
                p = 1 / (1 + np.exp(-np.clip(x @ weights, -30, 30)))
                penalty = .02 * weights
                penalty[0] = 0
                weights -= rate * (x.T @ (p - y) / len(y) + penalty)
                # More time cannot improve predicted recall without new evidence.
                weights[1] = max(0, weights[1])
                weights[2] = min(-.01, weights[2])
            self.weights = weights
            prediction = 1 / (1 + np.exp(-np.clip(x @ weights, -30, 30)))
            self.fit_brier = round(float(np.mean((prediction - y) ** 2)), 6)

    def probability(self, score, days):
        score = min(1., max(0., float(score)))
        days = max(0., float(days))
        if self.weights is None:
            return score * math.exp(-math.log(2) * days / (1 + 13 * score))
        value = float(np.dot(self.weights, [1, score, math.log1p(days)]))
        return 1 / (1 + math.exp(-max(-30, min(30, value))))

    def forecast(self, topic, now=None):
        now = now or datetime.now(timezone.utc)
        latest = self.latest.get(topic)
        if latest is None:
            return {'method': 'unassessed', 'probability': None, 'curve': [], 'review_in_days': 0}
        elapsed = max(0, (now - latest[0]).total_seconds() / 86400)
        score = latest[1]
        due = next((day for day in range(31) if self.probability(score, elapsed + day) < .7), 30)
        return {'method': 'fitted_assessment_model' if self.weights is not None else 'cold_start_heuristic',
                'probability': round(self.probability(score, elapsed), 4),
                'review_in_days': due, 'last_assessment_at': latest[0].isoformat(),
                'curve': [{'day': day, 'retention': round(100 * self.probability(score, elapsed + day), 1),
                           'review': False} for day in range(15)]}

    def diagnostics(self):
        return {'trained': self.weights is not None, 'training_pairs': len(self.samples),
                'weights': self.weights.tolist() if self.weights is not None else None,
                'training_brier': self.fit_brier, 'minimum_pairs': 20,
                'validation': 'in-sample fit only; no claim of predictive accuracy'}
