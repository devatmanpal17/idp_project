"""Bounded, expiring recall-priority cache for ACTIVE retrieval results only.

The budget counts serialized payload bytes, not total Python process RSS.
Values are deserialized on read so callers cannot mutate cached evidence.
"""
import json
import math
import time
from collections import OrderedDict
from threading import RLock
from .metrics import metrics


class VectorCache:
    def __init__(self, max_bytes=8 * 1024 * 1024, ttl_seconds=300, clock=time.monotonic):
        if max_bytes < 0 or ttl_seconds < 0:
            raise ValueError('Cache budgets must be nonnegative.')
        self.max_bytes, self.ttl_seconds, self.clock = max_bytes, ttl_seconds, clock
        self._entries = OrderedDict()
        self._bytes = 0
        self._lock = RLock()

    def _remove(self, key):
        _, payload, size, priority = self._entries.pop(key)
        self._bytes -= size

    def _expire(self):
        now = self.clock()
        for key, (expires, _, _, _) in list(self._entries.items()):
            if expires <= now:
                self._remove(key)
                metrics.add('cache_expirations')

    @property
    def resident_bytes(self):
        with self._lock:
            self._expire()
            return self._bytes

    def get(self, key):
        with self._lock:
            self._expire()
            item = self._entries.get(key)
            if item is None:
                metrics.add('cache_misses')
                return None
            self._entries.move_to_end(key)
            metrics.add('cache_hits')
            return json.loads(item[1])

    def put(self, key, value, priority=0.5):
        """Admit when the new result outranks victims; LRU breaks priority ties.

        A higher priority denotes a lower predicted recall and greater review
        need. Unassessed topics use the neutral default supplied by the caller.
        """
        priority = float(priority)
        if not math.isfinite(priority) or not 0 <= priority <= 1:
            raise ValueError('Cache priority must be between zero and one.')
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        size = len(payload) + len(key.encode('utf-8'))
        with self._lock:
            self._expire()
            if size > self.max_bytes or not self.ttl_seconds:
                return False
            old_size = self._entries[key][2] if key in self._entries else 0
            needed = max(0, self._bytes - old_size + size - self.max_bytes)
            victims = []
            if needed:
                # Sorting is stable, so the least recently used entry wins a
                # tie. Decide before removing anything: rejected admissions
                # must leave all existing evidence intact.
                candidates = sorted(
                    ((item_key, item[2], item[3]) for item_key, item in self._entries.items()
                     if item_key != key), key=lambda item: item[2])
                for item_key, item_size, item_priority in candidates:
                    if item_priority > priority:
                        metrics.add('cache_priority_rejections')
                        return False
                    victims.append(item_key)
                    needed -= item_size
                    if needed <= 0:
                        break
                if needed > 0:
                    return False
            if key in self._entries:
                self._remove(key)
            for victim in victims:
                self._remove(victim)
                metrics.add('cache_evictions')
            self._entries[key] = (self.clock() + self.ttl_seconds, payload, size, priority)
            self._bytes += size
            return True

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._bytes = 0
            metrics.add('cache_invalidations')

    def status(self):
        with self._lock:
            self._expire()
            return {'entries': len(self._entries), 'resident_bytes': self._bytes,
                    'max_bytes': self.max_bytes, 'ttl_seconds': self.ttl_seconds,
                    'admission': 'lower_predicted_recall_first; LRU_on_ties',
                    'accounting': 'serialized keys and payloads; excludes runtime overhead'}
