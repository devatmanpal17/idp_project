# Synthetic feature benchmarks

Run `python -m benchmarks.run_all --seed 0 --repeats 5` from the repository root.
Results are written to `benchmarks/results/<UTC timestamp>/` as raw JSON, CSV,
and a summary generated from the raw rows. `--real-ollama` records the local
`/api/ps` response but does not yet perform a real model latency comparison.

The generator uses NumPy's seeded normal distribution to make unit-length
64-dimensional corpus and query vectors at 1k, 10k, and 100k index sizes.
The lease simulation masks vectors with cosine at least 0.97 to a selected
evidence vector and compares top five leakage with an unmasked index. The
cache simulation inserts one new unit vector and compares each entry's exact
fifth score against flush-all, fixed-radius, and TTL baselines. The residency
trace is a fixed sequence of pause, play, hide, and pause intervals using a
mock transport. The granularity trace is a 120-second lesson with a 30-second
observed interval. The alignment trace repeats 200 synthetic one-second cues
with a known 37-second offset. All inputs and outputs are synthetic; the harness does not
establish real-world performance or patentability.
