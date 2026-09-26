"""Bounded, expiring LRU cache for ACTIVE retrieval results only.

The budget counts serialized payload bytes, not total Python process RSS.
Values are deserialized on read so callers cannot mutate cached evidence.
"""
import json
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
        _, payload, size = self._entries.pop(key)
        self._bytes -= size

    def _expire(self):
        now = self.clock()
        for key, (expires, _, _) in list(self._entries.items()):
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

    def put(self, key, value):
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        size = len(payload) + len(key.encode('utf-8'))
        with self._lock:
            self._expire()
            if key in self._entries:
                self._remove(key)
            if size > self.max_bytes or not self.ttl_seconds:
                return False
            while self._entries and self._bytes + size > self.max_bytes:
                self._remove(next(iter(self._entries)))
                metrics.add('cache_evictions')
            self._entries[key] = (self.clock() + self.ttl_seconds, payload, size)
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
                    'accounting': 'serialized keys and payloads; excludes runtime overhead'}
