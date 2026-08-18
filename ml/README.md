# Cognivue ML Engine

The `ml/` folder contains the Machine Learning, RAG vector retrieval, LLM generation, and adaptive difficulty calibration pipelines.

## Modules

- **`rag_engine.py`**: Tokenization, TF-IDF vector embeddings, cosine similarity search, and context chunk retrieval.
- **`llm_service.py`**: Prompt engineering and API clients for Google Gemini, OpenAI, and zero-key local generation fallback.
- **`calibration.py`**: Learner signal difficulty calibrator and Bayesian mastery update algorithms.
- **`knowledge_base.py`**: Multi-subject MOOC lecture transcript corpus.

## Usage

```python
from ml import rag_engine, llm_service, calibrate_difficulty

# 1. Retrieve context
chunks = rag_engine.retrieve(query="Kernel trick", topic="Support Vector Machines")

# 2. Calibrate difficulty
calibration = calibrate_difficulty(mastery_score=45.0)

# 3. Generate quiz
questions = llm_service.generate_quiz_with_rag(
    topic="Support Vector Machines",
    context_chunks=chunks,
    mastery_score=45.0,
    difficulty=calibration["difficulty"],
    count=3
)
```
