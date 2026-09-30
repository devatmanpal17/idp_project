"""Reproducible synthetic measurements; never substitutes for real Ollama trials."""
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def unit(rng, rows, dims=64):
    values = rng.standard_normal((rows, dims), dtype=np.float32)
    return values / np.maximum(np.linalg.norm(values, axis=1, keepdims=True), 1e-8)


def percentile(values, p):
    return float(np.percentile(values, p))


def memory_info():
    try:
        import psutil
        return {'ram_bytes': psutil.virtual_memory().total}
    except ImportError:
        return {'ram_bytes': None}


def run(seed, repeats, real_ollama=False):
    rng = np.random.default_rng(seed)
    rows = []
    for size in (1_000, 10_000, 100_000):
        for repeat in range(repeats):
            corpus = unit(rng, size)
            queries = unit(rng, min(1000, size // 10))
            evidence = corpus[0]
            # Ten percent of questions deliberately concern the leased evidence.
            focused = max(1, len(queries) // 10)
            queries[:focused] = evidence + 0.05 * unit(rng, focused)
            queries[:focused] /= np.linalg.norm(queries[:focused], axis=1, keepdims=True)
            start = time.perf_counter_ns()
            similarities = corpus @ evidence
            mask = similarities >= 0.97
            mask[0] = True
            demote_us = (time.perf_counter_ns() - start) / 1000
            start = time.perf_counter_ns()
            scores = queries @ corpus.T
            top = np.argpartition(scores, -5, axis=1)[:, -5:]
            no_mask_leak = float(np.any(np.isin(top, np.flatnonzero(mask)), axis=1).mean())
            masked = scores.copy()
            masked[:, mask] = -np.inf
            leased_top = np.argpartition(masked, -5, axis=1)[:, -5:]
            lease_leak = float(np.any(np.isin(leased_top, np.flatnonzero(mask)), axis=1).mean())
            rows.append(dict(feature='A', metric='leakage_rate', size=size, repeat=repeat,
                             baseline=no_mask_leak, invention=lease_leak,
                             unit='fraction', elapsed_us=(time.perf_counter_ns()-start)/1000))
            rows.append(dict(feature='A', metric='demote_check', size=size, repeat=repeat,
                             baseline=None, invention=demote_us, unit='microseconds', elapsed_us=demote_us))

            # Each cache entry's score is its exact fifth result. Inserting a new vector
            # changes that top five iff its cosine reaches the entry-specific boundary.
            kth = np.partition(scores, -5, axis=1)[:, -5]
            incoming = unit(rng, 1)[0]
            start = time.perf_counter_ns()
            insert_scores = queries @ incoming
            exact = insert_scores >= kth  # ties invalidate conservatively
            invalidate_us = (time.perf_counter_ns() - start) / 1000
            flush_all = np.ones_like(exact, dtype=bool)
            sphere = insert_scores >= 0.7
            ttl = np.zeros_like(exact, dtype=bool)  # insertion occurs inside TTL
            for label, predicted in [('exact', exact), ('flush_all', flush_all),
                                     ('sphere_0.7', sphere), ('ttl_60', ttl), ('ttl_300', ttl)]:
                rows.append(dict(feature='B', metric=f'{label}_false_negative', size=size,
                    repeat=repeat, baseline=None, invention=float(np.mean(exact & ~predicted)),
                    unit='fraction', elapsed_us=invalidate_us))
                rows.append(dict(feature='B', metric=f'{label}_false_positive', size=size,
                    repeat=repeat, baseline=None, invention=float(np.mean(~exact & predicted)),
                    unit='fraction', elapsed_us=invalidate_us))
            rows.append(dict(feature='B', metric='invalidation_check_per_1k', size=size,
                repeat=repeat, baseline=None, invention=invalidate_us / len(queries) * 1000,
                unit='microseconds', elapsed_us=invalidate_us))

    from ml.residency import ResidencyController
    from ml.transfer import _tokens, _shingles
    import difflib
    class Transport:
        def __init__(self): self.loaded = {}; self.actions = []
        def ps(self): return [{'name': k, 'size': v} for k, v in self.loaded.items()]
        def control(self, model, keep_alive, embed=False):
            self.actions.append((model, keep_alive))
            if keep_alive == '0': self.loaded.pop(model, None)
            else: self.loaded[model] = 4_000_000_000 if not embed else 1_000_000_000
    for repeat in range(repeats):
        now = [0.0]
        transport = Transport()
        controller = ResidencyController(transport, lambda: now[0])
        controller.budget_mb = 3500
        for state, duration in [('PAUSED', 20), ('PLAYING', 120), ('PAUSED', 25),
                                ('PLAYING', 90), ('HIDDEN', 80), ('PAUSED', 10)]:
            controller.transition(state)
            now[0] += duration
            controller.tick()
        rows.append(dict(feature='C', metric='mock_loads', size=0, repeat=repeat,
            baseline=None, invention=controller.loads, unit='count', elapsed_us=None))
        rows.append(dict(feature='C', metric='mock_unloads', size=0, repeat=repeat,
            baseline=None, invention=controller.unloads, unit='count', elapsed_us=None))

        # Synthetic seek: 30 of 120 seconds observed, one macro spans all 120;
        # six ten-second micro intervals have three eligible for retrieval.
        watched = [(45, 75)]
        micro_covered = sum(10 for start in range(0, 120, 10)
                            if start >= watched[0][0] and start + 10 <= watched[0][1])
        rows.append(dict(feature='E', metric='retrievable_watched_fraction', size=120,
            repeat=repeat, baseline=0.0, invention=micro_covered / 30,
            unit='fraction', elapsed_us=None))

        # An offset re-upload with exact transcript wording and known +37 s shift.
        source = [{'content': f'unique lecture point {i} copper circuit explanation',
                   't_start': i * 1000, 't_end': (i + 1) * 1000} for i in range(200)]
        target = [{**cue, 't_start': cue['t_start'] + 37000,
                   't_end': cue['t_end'] + 37000} for cue in source]
        a, b = _tokens(source), _tokens(target)
        start = time.perf_counter_ns()
        match = difflib.SequenceMatcher(None, [v[0] for v in a], [v[0] for v in b], autojunk=False)
        block = max(match.get_matching_blocks(), key=lambda item: item.size)
        measured_offset = b[block.b][1] - a[block.a][1]
        rows.append(dict(feature='D', metric='mapping_error_offset_reupload', size=200,
            repeat=repeat, baseline=None, invention=abs(measured_offset - 37000) / 1000,
            unit='seconds', elapsed_us=(time.perf_counter_ns() - start) / 1000))
        rows.append(dict(feature='D', metric='exact_text_vector_reuse_fraction', size=200,
            repeat=repeat, baseline=0.0,
            invention=len(_shingles(a) & _shingles(b)) / max(1, len(_shingles(b))),
            unit='fraction', elapsed_us=None))

    real = None
    if real_ollama:
        from ml.residency import OllamaTransport
        try:
            real = {'models': OllamaTransport().ps(), 'status': 'ps_checked'}
        except Exception as exc:
            real = {'status': 'unavailable', 'error': str(exc)}
    return rows, real


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--real-ollama', action='store_true')
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    rows, real = run(args.seed, args.repeats, args.real_ollama)
    destination = Path(__file__).parent / 'results' / started.strftime('%Y%m%dT%H%M%SZ')
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / 'raw.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    import chromadb
    metadata = {'synthetic': True, 'seed': args.seed, 'repeats': args.repeats,
        'started_at': started.isoformat(), 'platform': platform.platform(),
        'processor': platform.processor(), 'python': sys.version,
        'numpy': np.__version__, 'chromadb': chromadb.__version__,
        'ollama': real, **memory_info()}
    (destination / 'raw.json').write_text(json.dumps({'metadata': metadata, 'rows': rows}, indent=2), encoding='utf-8')
    grouped = {}
    for row in rows:
        if row['invention'] is not None:
            grouped.setdefault((row['feature'], row['metric'], row['size']), []).append(row['invention'])
    lines = ['# Synthetic benchmark summary', '',
        f'Seed {args.seed}; repeats {args.repeats}. These are measured calculations on synthetic vectors and traces, not real-model latency or patent performance claims.', '',
        '| Feature | Metric | Size | Mean ± std | p50 | p95 | p99 |',
        '|---|---|---:|---:|---:|---:|---:|']
    for (feature, metric, size), values in sorted(grouped.items()):
        lines.append(f'| {feature} | {metric} | {size} | {statistics.mean(values):.6g} ± {statistics.pstdev(values):.6g} | '
                     f'{percentile(values,50):.6g} | {percentile(values,95):.6g} | {percentile(values,99):.6g} |')
    lines.extend(['', 'Unavailable in this run: real Ollama first-token latency, HNSW disagreement, '
                  'and end-to-end Chroma demote/restore latency.'])
    (destination / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(destination)


if __name__ == '__main__':
    main()
