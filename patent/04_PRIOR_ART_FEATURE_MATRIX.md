# Feature-to-code matrix — 2026-09-27

This maps the supplied comparison language to the running ChaiGaram system.
The cited patents and papers describe other systems; their features are not
requirements to copy into this application. The distinctions below describe
code behavior and tested boundaries, not a conclusion about patentability.

| Supplied distinction or feature | Implementation | Verification |
| --- | --- | --- |
| A single playback position must not unlock skipped content; only observed intervals count | `extension/observation.js` samples decoded, visible playback and breaks traversal on seeks, stalls, rate changes and hiding. `ml/temporal.py` requires complete interval coverage. `ml/vector_state.py` records sessions. | `tests/observation.test.cjs`; `tests/test_vector_pipeline.py`; real Chrome seek-gap check in `results/browser_checks.json` |
| Future captions can be precomputed without entering retrieval | `ml/vector_state.py` persists future embeddings as `SEALED` in SQL; Chroma contains `ACTIVE` entries only. `backend/routes/vectors.py` admits work within a bounded future horizon. | Sealed-leakage and speculation tests; Chrome report shows one skipped caption `SEALED` and absent from retrieval. |
| Observation triggers promotion without re-inference | `VectorState.promote` writes `PROMOTION_PENDING`, upserts the persisted vector, then commits `ACTIVE`; restart replays pending intents. | `test_sealed_leakage_promotion_and_zero_inference` and crash-recovery tests in `tests/test_vector_pipeline.py` |
| Video tutor, summary and quiz may use only observed material | Video routes require an observation-tracked document; `RAGEngine.retrieve` searches the ACTIVE collection and scopes it to the document. | `test_all_generation_endpoints_receive_active_only` in `tests/test_vector_pipeline.py` |
| Worker termination must not lose jobs or completed embeddings | `ml/persistent_jobs.py`, `backend/routes/jobs.py` and the extension retry ID preserve input, stages, checkpoints and terminal results; persisted sealed vectors are reused after restart. | `tests/test_jobs_scheduler.py`, `tests/test_vector_pipeline.py`, `tests/extension_jobs.test.cjs` |
| Local resources bound future inference | `ml/scheduler.py` admits idle speculative batches using measured latency, queue depth, a future horizon and cache occupancy. Interactive work has separate worker capacity. | `tests/test_jobs_scheduler.py`, `tests/test_vector_pipeline.py` |
| Invalid quiz slots are repaired selectively | `ml/selective_repair.py` retains validated questions and regenerates only failed slots, with citation, exact-quote, duplicate and language checks. | `tests/test_cache_recall_repair.py`; live Chrome quiz and grading check |
| Predicted recall affects a memory-bounded cache over the observation-gated index | `ml/recall.py` forecasts from prior assessment outcomes. `ml/vector_cache.py` gives lower-recall topics higher admission and retention priority, then uses LRU on ties. `RAGEngine` uses separate byte-bounded caches for ACTIVE retrieval results and query vectors, and clears them after assessment or index mutation. | Priority/admission tests in `tests/test_cache_recall_repair.py`; ACTIVE retrieval and query-vector reuse tests in `tests/test_vector_pipeline.py` |

The earlier prototype's caption capture, document-scoped retrieval, citation
checking, answer withholding and rolling-caption deduplication remain useful,
but are not treated as new on their own. The specific changes above are the
interval gate, sealed/active lifecycle, zero-inference promotion, durable jobs,
selective repair, scheduling and recall-guided caches.

## Interpretation boundaries

- The extension's rendered/decoded-frame evidence is **client-reported**. The
  backend validates request structure and session sequence, but cannot attest
  that an untrusted client really displayed the frames. “Verified observed”
  must be read as verified by the shipped client logic, not tamperproof proof.
- Cache budgets count serialized keys and payloads, not the process's total
  resident memory. Recall estimates next assessment performance, not an
  independently measured human memory probability; cold starts are labelled.
- The Google structured-video document's word-level alignment and OCR,
  Microsoft's episode spoiler concealment, Amazon's third-party content
  suppression, and Dropbox's entity-permission RAG are **prior-art comparison
  subjects**, not features claimed to exist in ChaiGaram.
- The single-process job runner recovers local restarts, not a distributed
  worker failure; an interrupted model call can repeat before checkpointing.

## Referenced publications

- [Amazon, US 10,417,272 B1](https://patents.google.com/patent/US10417272B1/en),
  *System for suppressing output of content based on media access* (2019).
- [Google, US 12,169,522 B2](https://patents.google.com/patent/US12169522B2/en),
  [continuation US 12,613,915 B2](https://patents.google.com/patent/US12613915B2/en),
  and [US 2026/0267916 A1](https://patents.justia.com/patent/20260267916),
  *Structured video documents*. The 2026 application continues the 2024
  application through US 18/961,038.
- [Microsoft, US 11,568,009 B2](https://patents.google.com/patent/US11568009B2/en),
  *Spoiler prevention* (2023).
- [Dropbox, US 12,373,506 B1](https://patents.google.com/patent/US12373506B1/en),
  *Personalized retrieval-augmented generation system* (2025).
- [Settles and Meeder, ACL 2016](https://aclanthology.org/P16-1174/),
  *A Trainable Spaced Repetition Model for Language Learning*.
- [Song et al., NSDI 2020](https://www.usenix.org/conference/nsdi20/presentation/song),
  *Learning Relaxed Belady for Content Distribution Network Caching*.
