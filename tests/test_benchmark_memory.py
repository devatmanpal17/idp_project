import unittest
import numpy as np
from benchmarks.run_all import lease_statistics, unit


class BenchmarkMemoryTests(unittest.TestCase):
    def test_batched_metrics_match_dense_reference(self):
        rng = np.random.default_rng(714)
        corpus, queries = unit(rng, 150), unit(rng, 19)
        queries[0] = corpus[0]
        mask = np.arange(len(corpus)) < 9
        scores = queries @ corpus.T
        top = np.argsort(scores, axis=1)[:, -5:]
        masked = scores.copy()
        masked[:, mask] = -np.inf
        leased = np.argsort(masked, axis=1)[:, -5:]
        for size in (1, 7, 32):
            with self.subTest(batch_size=size):
                result = lease_statistics(corpus, queries, mask, batch_size=size)
                self.assertEqual(result['unmasked_leak'], float(np.any(mask[top], axis=1).mean()))
                self.assertEqual(result['masked_leak'], float(np.any(mask[leased], axis=1).mean()))
                self.assertEqual(result['available'], 1.0)
                self.assertEqual(result['recall'], 1.0)
                np.testing.assert_allclose(result['kth'], np.sort(scores, axis=1)[:, -5], atol=1e-7)
