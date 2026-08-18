"""
ChaiGaram ML — Dynamic Educational Graph & Chart Generator
Generates mathematical chart payloads:
1. Vector Cosine Similarity distribution across retrieved chunks
2. Item Response Theory (IRT) Characteristic Curve: P(theta) = 1 / (1 + exp(-a * (theta - b)))
3. Bloom's Taxonomy Cognitive Complexity radar/bar breakdown
4. Bayesian Knowledge Tracing (BKT) Mastery Progression & Shift
5. Concept Dependency Knowledge Graph
"""

import math
from typing import List, Dict, Any


def generate_similarity_distribution_chart(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generates bar chart series for vector cosine similarities of retrieved chunks."""
    chart_data = []
    for i, c in enumerate(chunks):
        chart_data.append({
            "chunk_id": c.get("chunk_id", f"C{i+1}"),
            "similarity": round(c.get("similarity", 0.75) * 100, 1),
            "timestamp": c.get("timestamp", "00:00"),
            "topic": c.get("topic", "Topic"),
            "token_count": c.get("token_count", 25)
        })
    return chart_data


def generate_irt_curve(difficulty: float, mastery_score: float) -> List[Dict[str, Any]]:
    """
    Item Response Theory (2PL) Characteristic Curve.
    P(theta) = 1 / (1 + exp(-1.7 * a * (theta - b)))
    theta: learner ability (-3.0 to +3.0, mapped from mastery 0-100)
    b: item difficulty (-2.0 to +2.0, mapped from difficulty 0.0-1.0)
    a: item discrimination factor (1.4)
    """
    a = 1.4
    # Map difficulty [0.0, 1.0] to b [-2.0, 2.0]
    b = (difficulty - 0.5) * 4.0

    points = []
    for theta_val in range(0, 101, 10):
        # Map mastery [0, 100] to theta [-3.0, 3.0]
        theta = ((theta_val / 100.0) - 0.5) * 6.0
        prob = 1.0 / (1.0 + math.exp(-1.7 * a * (theta - b)))
        prob_pct = round(prob * 100, 1)

        points.append({
            "mastery": theta_val,
            "success_probability": prob_pct,
            "current_learner": theta_val == round(mastery_score / 10) * 10
        })
    return points


def generate_cognitive_breakdown(difficulty: float) -> List[Dict[str, Any]]:
    """
    Bloom's Revised Taxonomy cognitive load distribution based on difficulty.
    Levels: Remember, Understand, Apply, Analyze, Evaluate, Create
    """
    if difficulty < 0.40:
        # Foundational Recall
        distribution = [
            {"dimension": "Remember", "weight": 45, "target": 40},
            {"dimension": "Understand", "weight": 35, "target": 30},
            {"dimension": "Apply", "weight": 15, "target": 20},
            {"dimension": "Analyze", "weight": 5, "target": 10},
        ]
    elif difficulty < 0.65:
        # Intermediate Comprehension & Application
        distribution = [
            {"dimension": "Remember", "weight": 20, "target": 20},
            {"dimension": "Understand", "weight": 35, "target": 35},
            {"dimension": "Apply", "weight": 30, "target": 30},
            {"dimension": "Analyze", "weight": 15, "target": 15},
        ]
    else:
        # Advanced Synthesis & Evaluation
        distribution = [
            {"dimension": "Remember", "weight": 10, "target": 15},
            {"dimension": "Understand", "weight": 20, "target": 25},
            {"dimension": "Apply", "weight": 35, "target": 30},
            {"dimension": "Analyze", "weight": 35, "target": 30},
        ]
    return distribution


def generate_mastery_shift_chart(
    previous_mastery: float,
    new_mastery: float,
    score_pct: float
) -> List[Dict[str, Any]]:
    """Generates comparison series showing mastery progression and retention trajectory."""
    delta = new_mastery - previous_mastery
    return [
        {"metric": "Pre-Quiz Mastery", "value": round(previous_mastery, 1), "fill": "#8884d8"},
        {"metric": "Quiz Score", "value": round(score_pct, 1), "fill": "#00C49F"},
        {"metric": "Post-Quiz Mastery", "value": round(new_mastery, 1), "fill": "#0088FE"},
    ]


def generate_concept_graph(topic: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generates concept nodes and dependency links for knowledge graph visualization."""
    nodes = [
        {"id": "root", "label": topic, "group": "core", "size": 24}
    ]
    links = []

    for i, c in enumerate(chunks[:5]):
        node_id = f"concept_{i+1}"
        # Extract short label from snippet
        words = c.get("snippet", "").split()
        label = " ".join(words[:3]) if len(words) >= 3 else f"Concept {i+1}"

        nodes.append({
            "id": node_id,
            "label": label,
            "group": "subconcept",
            "similarity": round(c.get("similarity", 0.8) * 100, 0),
            "size": 16
        })
        links.append({
            "source": "root",
            "target": node_id,
            "value": round(c.get("similarity", 0.8) * 10, 1)
        })

    return {"nodes": nodes, "links": links}
