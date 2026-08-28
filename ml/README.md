# ChaiGaram ML Engine

The `ml/` folder contains the Machine Learning, RAG vector retrieval, LLM generation, and adaptive difficulty calibration pipelines.

## Modules

- **`rag_engine.py`**: Overlapping semantic chunking, Ollama embeddings, persistent ChromaDB indexing, metadata filtering, and raw cosine retrieval.
- **`llm_service.py`**: Local Llama generation through Ollama with Pydantic JSON schemas and citation allow-list validation.
- **`analytics.py`**: Server-side quiz sessions and persisted SQLite attempt/mastery history.
- **`calibration.py`**: Learner signal difficulty calibrator and Bayesian mastery update algorithms.

## Usage

```python
from ml import rag_engine, llm_service, calibrate_difficulty

rag_engine.ingest_document(
    text="Your trusted lesson or transcript...",
    topic="Your topic",
    source="Lecture 1",
)

# 1. Retrieve context
chunks = rag_engine.retrieve(query="Explain the main idea", topic="Your topic")

# 2. Calibrate difficulty
calibration = calibrate_difficulty(mastery_score=45.0)

# 3. Generate quiz
questions = llm_service.generate_quiz_with_rag(
    topic="Your topic",
    context_chunks=chunks,
    mastery_score=45.0,
    difficulty=calibration["difficulty"],
    count=3
)
```
