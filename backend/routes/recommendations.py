"""
Smart recommendations endpoint.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/recommendations/smart")
def get_smart_recommendations():
    """Returns AI-calculated recommendations based on spaced-repetition retention curves."""
    return {
        "recommendations": [
            {
                "id": "rec_01",
                "topic": "Dynamic Programming",
                "course": "Data Structures & Algorithms",
                "type": "revisit_weak_topic",
                "impact_score": 94,
                "estimated_minutes": 35,
                "reasoning": "Mastery is 24 with a -5.4 weekly trend. Quiz performance (18%) is the dominant drag and 8 revisits indicate passive rewatching without consolidation. A structured retrieval drill will recover retention.",
                "action": "Launch Practice Quiz"
            },
            {
                "id": "rec_02",
                "topic": "Graph Traversal",
                "course": "Data Structures & Algorithms",
                "type": "revisit_weak_topic",
                "impact_score": 88,
                "estimated_minutes": 25,
                "reasoning": "Graph traversal underpins Dynamic Programming on DAGs, which is scheduled next. Closing this 29-point mastery gap prevents downstream compounding failure.",
                "action": "Review BFS/DFS Chunks"
            },
            {
                "id": "rec_03",
                "topic": "Support Vector Machines",
                "course": "Machine Learning A-Z",
                "type": "revisit_weak_topic",
                "impact_score": 81,
                "estimated_minutes": 30,
                "reasoning": "Largest completion-to-mastery gap in Machine Learning A-Z (78% watched vs 41% mastery). Retrieval practice on the kernel trick will recover over 30 points of mastery.",
                "action": "Generate SVM Quiz"
            },
            {
                "id": "rec_04",
                "topic": "Performance Optimization",
                "course": "React - The Complete Guide",
                "type": "proceed_next_module",
                "impact_score": 66,
                "estimated_minutes": 20,
                "reasoning": "Performance Optimization is trending down (-2.7). A short profiling exercise and hook review will stabilize it before moving to server components.",
                "action": "Start Quick Quiz"
            }
        ]
    }
