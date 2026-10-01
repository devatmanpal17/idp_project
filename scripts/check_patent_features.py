"""Real Ollama/SQLite/Chroma acceptance checks for F1 and features A, B, D, E.

Run from the repository root. Uses disposable databases and synthetic captions;
the live residency policy is covered separately by test_residency.py and benchmarks.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'benchmarks/results/patent-live/live_features.json')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {'kind': 'real local patent-feature acceptance with synthetic captions',
              'started_at': datetime.now(timezone.utc).isoformat(), 'checks': []}

    def check(name, action):
        started = time.perf_counter()
        try:
            details = action()
            report['checks'].append({'name': name, 'passed': True,
                                    'seconds': time.perf_counter() - started, 'details': details})
            print(name + ': passed', flush=True)
            return details
        except Exception as exc:
            report['checks'].append({'name': name, 'passed': False, 'error': str(exc)})
            raise
        finally:
            args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        os.environ.update(DATABASE_URL=f'sqlite:///{(root / "state.db").as_posix()}',
                          CHROMA_PERSIST_DIR=str(root / 'chroma'))
        from sqlalchemy import text
        from ml import rag_engine as rag, llm_service
        from ml.metrics import metrics
        from ml.rag_engine import RAGEngine
        from backend.models import AskRequest
        from backend.routes.rag import ask_lesson

        report.update(embedding_model=rag.model_version, chat_model=llm_service.model)
        learner, video, copy = 'patent-live-learner', 'youtube:patent-live', 'youtube:patent-copy'
        lessons = [
            'Binary search requires a sorted sequence. At each step it compares the middle value '
            'with the target. If the target is smaller it keeps the left half; otherwise it keeps '
            'the right half. Repeating this operation reduces the remaining candidates logarithmically.',
            'A stack uses last in first out order. Push adds an element to the top and pop removes '
            'the top element. This order lets a program undo recent operations first. An empty '
            'stack must be checked before attempting to remove an element.',
            'A queue uses first in first out order. Enqueue adds an element to the back and dequeue '
            'removes an element from the front. Tasks are therefore processed in their arrival order. '
            'Queue operations should also handle the empty collection without removing an element.',
            'The unwatched final caption contains the unrelated secret phrase copper lantern. '
            'This phrase must remain outside searchable evidence until the final interval is observed.'
        ]
        cues = [{'start': i * 2, 'end': (i + 1) * 2, 'text': content}
                for i, content in enumerate(lessons)]

        def calls():
            return metrics.snapshot().get('embedding_calls_total', 0)

        def sealed():
            result = rag.scoped.seal(learner, video, cues, 8)
            assert result['sealed_added'] > 0
            assert rag.scoped.retrieve(learner, video, 'binary search') == []
            assert rag.count == 0
            return result
        seal = check('F1_real_vectors_remain_sealed', sealed)

        def observe_opening():
            before = calls()
            result = rag.scoped.intervals(learner, video, 1,
                [{'start': 0, 'end': 2, 'wall_ms': 2000, 'rate': 1}], revision=seal['revision'])
            assert calls() == before, 'Promotion repeated embedding inference'
            chunks = rag.scoped.retrieve(learner, video, 'binary search')
            assert chunks and all('copper lantern' not in item['snippet'] for item in chunks)
            assert all('first in first out' not in item['snippet'] for item in chunks)
            return result
        check('F1_E_partial_coverage_reuses_vectors_without_parent_leakage', observe_opening)

        def transferred():
            before = calls()
            shifted = [{**cue, 'start': cue['start'] + 37, 'end': cue['end'] + 37} for cue in cues]
            result = rag.scoped.seal(learner, copy, shifted, 45)
            assert calls() == before, 'An identical re-upload was re-embedded'
            chunks = rag.scoped.retrieve(learner, copy, 'binary search')
            assert chunks and all('copper lantern' not in item['snippet'] for item in chunks)
            return result
        check('D_observed_reupload_transfer_reuses_real_vectors', transferred)

        def cached():
            request = AskRequest(question='What does binary search require?', source_type='video',
                                 learner_key=learner, video_key=video, top_k=1)
            first = ask_lesson(request)
            before = calls()
            hits = rag.answer_cache.hits
            assert ask_lesson(request) == first
            assert rag.answer_cache.hits == hits + 1
            assert calls() == before, 'A valid answer-cache hit embedded the query'
            return {'cache': rag.answer_cache.status(), 'answer': first['answer']}
        check('B_real_answer_cache_hit_skips_embedding_and_generation', cached)

        original = rag.scoped.retrieve(learner, video, 'binary search')
        questions = [{'citations': [original[0]['chunk_id']]}]

        def leased():
            rag.leases.open_scoped('patent-live-quiz', learner, video, questions)
            assert rag.scoped.retrieve(learner, video, 'binary search') == []
            assert rag.scoped.retrieve(learner, copy, 'binary search') == []
            assert not set(item['chunk_id'] for item in original).intersection(
                rag.collection.get(include=[])['ids'])
            return {'open_leases': rag.leases.status()}
        check('A_lease_hides_source_and_aligned_copy', leased)

        def recovered():
            # Follow production startup so the Ollama digest is resolved again.
            # Injected embedders intentionally use their declared test version.
            restarted = RAGEngine(root / 'chroma', state_engine=rag.vectors.engine)
            assert restarted.model_version == rag.model_version
            assert restarted.scoped.retrieve(learner, video, 'binary search') == []
            assert restarted.scoped.retrieve(learner, copy, 'binary search') == []
            with rag.vectors.engine.connect() as db:
                before_vectors = dict(db.execute(text("""SELECT chroma_id,vector FROM scoped_chunks
                    WHERE learner_key=:learner"""), {'learner': learner}).all())
            before = calls()
            restarted.leases.close('patent-live-quiz')
            assert calls() == before, 'Lease restoration re-embedded evidence'
            with rag.vectors.engine.connect() as db:
                after_vectors = dict(db.execute(text("""SELECT chroma_id,vector FROM scoped_chunks
                    WHERE learner_key=:learner"""), {'learner': learner}).all())
            assert after_vectors == before_vectors, 'Restoration changed stored vector bytes or IDs'
            restored = restarted.scoped.retrieve(learner, video, 'binary search')
            assert restored == original, {'original': original, 'restored': restored,
                                         'counts': restarted.scoped.status(learner, video)}
            return {'restored_vectors': restarted.count}
        check('A_restart_recovery_and_restoration', recovered)

        def entire_video():
            rag.scoped.intervals(learner, video, 2,
                [{'start': 2, 'end': 8, 'wall_ms': 6000, 'rate': 1}], revision=seal['revision'])
            chunks = rag.scoped.retrieve(learner, video, 'binary search')
            assert any('copper lantern' in item['snippet'] for item in chunks)
            with rag.vectors.engine.connect() as db:
                active_macros = db.execute(text("""SELECT COUNT(*) FROM scoped_chunks
                    WHERE video_key=:video AND state='ACTIVE' AND granularity='macro'"""),
                    {'video': video}).scalar_one()
            assert active_macros > 0
            return {'active_macros': active_macros}
        check('E_full_coverage_unlocks_parent_macros', entire_video)

        def revised():
            changed = [{**cue, 'text': f'Unrelated replacement botany section {i} about leaf tissue.'}
                       for i, cue in enumerate(cues)]
            result = rag.scoped.seal(learner, video, changed, 8)
            assert rag.scoped.retrieve(learner, video, 'binary search') == []
            assert rag.scoped.retrieve(learner, copy, 'binary search') == []
            try:
                rag.scoped.intervals(learner, video, 3,
                    [{'start': 0, 'end': 8, 'wall_ms': 8000, 'rate': 1}], revision=seal['revision'])
            except ValueError:
                pass
            else:
                raise AssertionError('A stale revision observation was accepted')
            return result
        check('F1_D_revision_revokes_transfer_and_rejects_stale_intervals', revised)

        report['success'] = True
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        rag.vectors.engine.dispose()


if __name__ == '__main__':
    main()
