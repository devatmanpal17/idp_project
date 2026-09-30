"""Run real Ollama embedding/answer/summary/quiz checks in isolated temporary stores."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    results = {'kind': 'real local Ollama smoke test', 'checks': []}
    output = Path(os.getenv('CHAI_LIVE_CHECK_OUTPUT', str(ROOT / 'patent/results/live_models.json')))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        os.environ['DATABASE_URL'] = f'sqlite:///{(root / "analytics.db").as_posix()}'
        os.environ['CHROMA_PERSIST_DIR'] = str(root / 'chroma')
        from ml import rag_engine, llm_service
        results['embedding_model'] = rag_engine.embeddings.model
        results['chat_model'] = llm_service.model
        lesson = ('Binary search works on a sorted sequence and repeatedly cuts the search interval in half. '
                  'It compares the middle value with the target value. If the target is smaller, the search '
                  'continues in the left half. If the target is larger, it continues in the right half. '
                  'The process ends when the target is found or the interval is empty. '
                  'Before searching, the values must be sorted in ascending order; otherwise a midpoint '
                  'comparison cannot identify which half may contain the target. Each comparison removes '
                  'roughly half of the remaining candidates, so the number of comparisons grows '
                  'logarithmically with the number of values. For example, a sorted collection of 1024 '
                  'values needs at most about ten halving steps to isolate one position. When the target '
                  'is absent, the lower bound eventually passes the upper bound and the algorithm reports '
                  'that no matching value was found. A sequential scan does not need sorted input, but it '
                  'may inspect every value before reaching the target or proving it absent.')
        def check(name, action):
            started = time.perf_counter()
            try:
                value = action()
                results['checks'].append({'name': name, 'passed': True, 'seconds': time.perf_counter() - started})
                print(name + ': passed', flush=True)
                return value
            except Exception as exc:
                results['checks'].append({'name': name, 'passed': False, 'error': str(exc),
                                          'cause': str(exc.__cause__) if exc.__cause__ else None,
                                          'seconds': time.perf_counter() - started})
                raise
            finally:
                output.write_text(json.dumps(results, indent=2), encoding='utf-8')
        doc = check('document_embedding', lambda: rag_engine.ingest_document(lesson, 'Binary search', 'Smoke-test lesson'))
        chunks = check('retrieval', lambda: rag_engine.retrieve('How does binary search work?', document_id=doc['document_id']))
        assert chunks
        answer = check('grounded_answer', lambda: llm_service.answer_with_rag('How does binary search reduce the interval?', chunks))
        assert answer
        check('summary', lambda: llm_service.summarize_with_rag('Binary search', chunks))
        quiz = check('grounded_quiz', lambda: llm_service.generate_quiz_with_rag('Binary search', chunks, 30, .4, 3))
        assert len(quiz) == 3
        results['quiz_question'] = quiz[0]['q']
        output.write_text(json.dumps(results, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
