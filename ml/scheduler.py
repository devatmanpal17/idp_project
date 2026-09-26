"""Measured-cost speculation budget and interactive-work admission gate."""
from contextlib import contextmanager
from threading import RLock
import time
from .metrics import metrics


class ResourceController:
    def __init__(self, ram_budget=64 * 1024 * 1024, horizon_ms=300_000, clock=time.monotonic):
        self.ram_budget, self.horizon_ms = ram_budget, horizon_ms
        self.ewma_ms = None
        self.interactive = 0
        self.lock = RLock()
        self.clock, self.last_probe = clock, None

    @contextmanager
    def interactive_work(self):
        with self.lock:
            self.interactive += 1
        try:
            yield
        finally:
            with self.lock:
                self.interactive -= 1

    def measured(self, elapsed_ms):
        with self.lock:
            self.ewma_ms = elapsed_ms if self.ewma_ms is None else .25 * elapsed_ms + .75 * self.ewma_ms

    def decide(self, *, budget_ms, idle, queue_depth=0, occupancy=0):
        with self.lock:
            capacity = max(0, (self.ram_budget - occupancy) // (8 * 4096))
            if not idle or self.interactive or queue_depth > 2 or capacity == 0 or budget_ms <= 0:
                size, reason = 0, 'busy_or_memory_budget'
            elif self.ewma_ms is None:
                size, reason = 1, 'cold_start_probe'
                self.last_probe = self.clock()
            else:
                # At most 8 per request; budget reduced for queue contention.
                size = min(8, int(budget_ms / (max(self.ewma_ms, 1) * (queue_depth + 1))),
                           capacity)
                reason = 'measured_budget'
                # A cold model load may exceed the normal idle budget. Re-probe
                # occasionally so that estimate cannot permanently starve work.
                if size == 0 and (self.last_probe is None or self.clock() - self.last_probe >= 30):
                    size, reason = 1, 'cost_recovery_probe'
                    self.last_probe = self.clock()
            decision = {'batch_size': size, 'reason': reason, 'estimated_chunk_ms': self.ewma_ms,
                        'budget_ms': budget_ms, 'queue_depth': queue_depth, 'cache_bytes': occupancy,
                        'horizon_ms': self.horizon_ms, 'concurrent_embedding_jobs': 1}
            metrics.add('scheduler_decisions')
            self.last_decision = decision
            return decision


controller = ResourceController()
