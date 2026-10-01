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
        if sys.platform == 'win32':
            import ctypes
            class MemoryStatus(ctypes.Structure):
                _fields_ = [('length', ctypes.c_ulong), ('memory_load', ctypes.c_ulong),
                    ('total_phys', ctypes.c_ulonglong), ('avail_phys', ctypes.c_ulonglong),
                    ('total_page', ctypes.c_ulonglong), ('avail_page', ctypes.c_ulonglong),
                    ('total_virtual', ctypes.c_ulonglong), ('avail_virtual', ctypes.c_ulonglong),
                    ('avail_extended', ctypes.c_ulonglong)]
            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return {'ram_bytes': status.total_phys}
        return {'ram_bytes': None}


def ollama_info():
    import urllib.request
    base = os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434').rstrip('/')
    try:
        with urllib.request.urlopen(base + '/api/version', timeout=3) as response:
            version = json.load(response).get('version')
        with urllib.request.urlopen(base + '/api/tags', timeout=3) as response:
            tags = [model.get('name') for model in json.load(response).get('models', [])]
        return {'version': version, 'model_tags': tags}
    except Exception as exc:
        return {'status': 'unavailable', 'error': str(exc)}


def real_residency_trials(repeats):
    """Short local pause traces; models are explicitly reset between trials."""
    import urllib.request
    from ml.residency import OllamaTransport, ResidencyController, canonical_model

    transport = OllamaTransport()
    llm = os.getenv('OLLAMA_CHAT_MODEL', 'llama3.2:3b')
    embedder = os.getenv('OLLAMA_EMBED_MODEL', 'embeddinggemma')
    base = transport.base
    rows = []
    trace = []
    for repeat in range(repeats):
        for mode in ('cold_after_unload', 'fixed_10m_warm', 'controller_pause_preload'):
            transport.control(llm, '0')
            transport.control(embedder, '-1', embed=True)
            prepare_start = time.perf_counter()
            if mode == 'fixed_10m_warm':
                transport.control(llm, '10m')
            elif mode == 'controller_pause_preload':
                controller = ResidencyController(transport=transport)
                controller.transition('PAUSED')
            preparation_ms = (time.perf_counter() - prepare_start) * 1000
            resident_before = transport.ps()
            present = {canonical_model(item.get('name', item.get('model', '')))
                       for item in resident_before}
            if mode != 'cold_after_unload' and canonical_model(llm) not in present:
                raise RuntimeError(f'{mode} failed to preload the chat model')
            before_bytes = sum(int(item.get('size', 0)) for item in resident_before)
            body = {'model': llm, 'prompt': 'In one sentence, explain binary search.',
                    'stream': True, 'options': {'num_predict': 32},
                    'keep_alive': '10m' if mode != 'controller_pause_preload'
                    else controller.keep_alive(llm)}
            request = urllib.request.Request(base + '/api/generate',
                data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'},
                method='POST')
            start = time.perf_counter()
            first_ms = None
            final = None
            with urllib.request.urlopen(request, timeout=180) as response:
                for line in response:
                    item = json.loads(line)
                    if first_ms is None and item.get('response'):
                        first_ms = (time.perf_counter() - start) * 1000
                    if item.get('done'):
                        final = item
            total_ms = (time.perf_counter() - start) * 1000
            if first_ms is None or final is None:
                raise RuntimeError('Ollama did not return a generated token and final timing')
            after_bytes = sum(int(item.get('size', 0)) for item in transport.ps())
            measurements = {
                'first_token_ms': first_ms, 'question_latency_ms': total_ms,
                'load_duration_ms': final.get('load_duration', 0) / 1_000_000,
                'resident_after_pause_mb': before_bytes / (1024 * 1024),
                'peak_sampled_resident_mb': max(before_bytes, after_bytes) / (1024 * 1024),
                'preparation_ms': preparation_ms,
                'control_loads': controller.loads if mode == 'controller_pause_preload' else 0,
                'control_unloads': controller.unloads if mode == 'controller_pause_preload' else 0,
            }
            trace.append({'repeat': repeat, 'mode': mode, **measurements})
            for metric, value in measurements.items():
                rows.append(dict(feature='C', metric=f'real_{mode}_{metric}', size=0,
                                 repeat=repeat, baseline=None, invention=value,
                                 unit='milliseconds' if metric.endswith('_ms') else
                                      'megabytes' if metric.endswith('_mb') else 'count',
                                 elapsed_us=None))
    return rows, {'status': 'measured', 'trace': trace,
                  'conditions': 'Explicit unload between short pause trials; fixed 10m is preloaded; controller preloads at pause. This does not simulate a 10 minute watch.'}


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
            rows.append(dict(feature='A', metric='global_disable_leakage_rate', size=size,
                repeat=repeat, baseline=0.0, invention=0.0, unit='fraction', elapsed_us=None))
            rows.append(dict(feature='A', metric='available_retrieval_fraction', size=size,
                repeat=repeat, baseline=0.0,
                invention=float(np.isfinite(np.max(masked, axis=1)).mean()),
                unit='fraction', elapsed_us=None))
            restored_top = np.argpartition(scores, -5, axis=1)[:, -5:]
            rows.append(dict(feature='A', metric='restored_recall_at_5', size=size,
                repeat=repeat, baseline=1.0,
                invention=float(np.mean([len(set(a) & set(b)) / 5
                    for a, b in zip(top, restored_top)])), unit='fraction', elapsed_us=None))
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
            rows.append(dict(feature='B', metric='valid_entry_fraction_after_insert', size=size,
                repeat=repeat, baseline=0.0, invention=float(np.mean(~exact)),
                unit='fraction', elapsed_us=None))

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
        try:
            real_rows, real = real_residency_trials(repeats)
            rows.extend(real_rows)
        except Exception as exc:
            real = {'status': 'unavailable', 'error': str(exc)}
    return rows, real


def write_summary(destination, rows, seed, repeats, real):
    grouped = {}
    for row in rows:
        if row['invention'] is not None:
            group = grouped.setdefault((row['feature'], row['metric'], row['size']),
                                       {'baseline': [], 'invention': []})
            group['invention'].append(row['invention'])
            if row['baseline'] is not None:
                group['baseline'].append(row['baseline'])
    lines = ['# Feature benchmark summary', '',
        f'Seed {seed}; repeats {repeats}. Synthetic rows use generated vectors and traces. Real C rows, when present, use local Ollama.', '',
        '| Feature | Metric | Size | Baseline mean plus/minus std | Invention mean plus/minus std | p50 | p95 | p99 |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for (feature, metric, size), group in sorted(grouped.items()):
        values = group['invention']
        baseline = group['baseline']
        base_text = (f'{statistics.mean(baseline):.6g} plus/minus {statistics.pstdev(baseline):.6g}'
                     if baseline else 'n/a')
        lines.append(f'| {feature} | {metric} | {size} | {base_text} | '
                     f'{statistics.mean(values):.6g} plus/minus {statistics.pstdev(values):.6g} | '
                     f'{percentile(values,50):.6g} | {percentile(values,95):.6g} | {percentile(values,99):.6g} |')
    lines.extend(['', f"Real Ollama trace: {real['status'] if real else 'not requested'}.",
                  'Unavailable in this run: HNSW disagreement and end-to-end Chroma demote/restore latency.'])
    (destination / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


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
        'ollama': ollama_info(), 'real_trial': real, **memory_info()}
    (destination / 'raw.json').write_text(json.dumps({'metadata': metadata, 'rows': rows}, indent=2), encoding='utf-8')
    write_summary(destination, rows, args.seed, args.repeats, real)
    print(destination)


if __name__ == '__main__':
    main()
