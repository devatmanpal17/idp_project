# Synthetic feature benchmarks

Run `python -m benchmarks.run_all --seed 0 --repeats 5` from the repository root.
Results are written to `benchmarks/results/<UTC timestamp>/` as raw JSON, CSV,
and a summary generated from the raw rows. Add `--real-ollama` for short,
sequential local model timing trials. That mode explicitly unloads the chat
model between cold, fixed 10-minute warm, and controller pause-preload trials.
It records first-token time, total question time, Ollama load duration, sampled
resident memory, preparation time, and controller load/unload counts. These are
short pause trials, not a simulated 10-minute viewing session.

The generator uses NumPy's seeded normal distribution to make unit-length
64-dimensional corpus and query vectors at 1k, 10k, and 100k index sizes.
Score, masking, and partition scratch matrices are evaluated in batches of 32
queries. This bounds scratch memory by the batch rather than the entire workload;
the JSON metadata records the batch size. A regression compares the metrics and
fifth-score boundaries with a dense reference. Timing results from older dense
runs and batched runs describe different harness implementations.
The lease simulation masks vectors with cosine at least 0.97 to a selected
evidence vector and compares top five leakage with an unmasked index and a
globally disabled assistant. It also records retrievable query fraction and
recall after restoring the original matrix. The
cache simulation inserts one new unit vector and compares each entry's exact
fifth score against flush-all, fixed-radius, and TTL baselines. The residency
trace is a fixed sequence of pause, play, hide, and pause intervals using a
mock transport. The granularity trace is a 120-second lesson with a 30-second
observed interval. The alignment trace repeats 200 synthetic one-second cues
with a known 37-second offset. All inputs and outputs are synthetic; the harness does not
establish real-world performance or patentability. A live Ollama run measures
the current local machine and models only; its three conditions begin from
different declared load states and should not be read as a general speedup.
