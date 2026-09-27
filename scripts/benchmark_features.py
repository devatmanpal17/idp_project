"""Reproducible local microbenchmark; synthetic embeddings are explicitly labelled."""
import argparse
import csv
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'patent/results')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        os.environ['DATABASE_URL'] = f'sqlite:///{(root / "analytics.db").as_posix()}'
        os.environ['CHROMA_PERSIST_DIR'] = str(root / 'default_chroma')
        os.environ['MPLCONFIGDIR'] = str(root / 'matplotlib')
        from sqlalchemy import create_engine
        from ml.rag_engine import RAGEngine
        from ml.temporal import Caption, Interval
        from ml.metrics import metrics
        class Embeddings:
            model = 'synthetic-benchmark-v1'
            calls = 0
            def embed(self, texts):
                self.calls += 1
                return [[1., 0., 0.] for _ in texts]
        embed = Embeddings()
        db = create_engine(f'sqlite:///{(root / "benchmark.db").as_posix()}')
        rag = RAGEngine(root / 'chroma', state_engine=db, embeddings=embed)
        doc = rag.ingest_document('Binary search halves the interval of a sorted sequence.', 'Search', 'Benchmark')
        rows = []
        modes = ('no_caches', 'query_vector_only', 'both_caches')
        for mode in modes:
            rag.hot_cache.clear()
            rag.query_vector_cache.clear()
            for trial in range(30):
                if mode != 'both_caches':
                    rag.hot_cache.clear()
                if mode == 'no_caches':
                    rag.query_vector_cache.clear()
                before = embed.calls
                started = time.perf_counter()
                result = rag.retrieve('binary search', document_id=doc['document_id'])
                rows.append({'mode': mode, 'trial': trial, 'ms': (time.perf_counter() - started) * 1000,
                             'embedding_calls': embed.calls - before, 'results': len(result)})
        media = rag.vectors.register('https://benchmark.invalid/video', 'Secret', [
            Caption(start_ms=0, end_ms=1000, text='A synthetic secret phrase appears here.')])['document_id']
        for chunk in rag.vectors.pending(media):
            rag.vectors.embed_chunk(media, chunk['id'])
        sealed_results = rag.retrieve('secret', document_id=media)
        before = embed.calls
        started = time.perf_counter()
        rag.vectors.observe(media, 'benchmark-session', 1, [Interval(start_ms=0, end_ms=1000)], 'rendered-frame')
        promotion = {'ms': (time.perf_counter() - started) * 1000,
                     'embedding_calls': embed.calls - before, 'sealed_results': len(sealed_results)}
        assert promotion['embedding_calls'] == 0 and not sealed_results
        summary = {'kind': 'synthetic-embedding microbenchmark; not real-model speedup evidence',
                   'trials_per_mode': 30, 'promotion': promotion, 'metrics': metrics.snapshot(),
                   'cache': rag.hot_cache.status(), 'retrieval': {}}
        for mode in modes:
            subset = [r for r in rows if r['mode'] == mode]
            summary['retrieval'][mode] = {'median_ms': statistics.median(r['ms'] for r in subset),
                                         'embedding_calls': sum(r['embedding_calls'] for r in subset)}
        with (args.output / 'retrieval_trials.csv').open('w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        (args.output / 'benchmark.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        figure, axes = plt.subplots(1, 2, figsize=(9, 3.5), layout='constrained')
        labels = ['No caches', 'Query vector', 'Both caches']
        axes[0].bar(labels, [summary['retrieval'][m]['median_ms'] for m in modes],
                    color=['#64748b', '#2e749c', '#0d9488'])
        axes[0].set(ylabel='Median latency (ms)', title='30 repeated scoped queries')
        axes[1].bar(labels, [summary['retrieval'][m]['embedding_calls'] for m in modes],
                    color=['#64748b', '#2e749c', '#0d9488'])
        axes[1].set(ylabel='Embedding calls', title='Calls across all 30 queries')
        figure.suptitle('Local microbenchmark — synthetic embeddings, real SQLite/Chroma')
        figure.savefig(args.output / 'benchmark.png', dpi=160)
        plt.close(figure)
        db.dispose()
        print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
