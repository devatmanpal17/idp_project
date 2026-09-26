"""Process-local counters, with no captured lesson text in logs."""
from collections import Counter
from threading import RLock


class Metrics:
    def __init__(self):
        self._values = Counter()
        self._lock = RLock()

    def add(self, key: str, value: float = 1):
        with self._lock:
            self._values[key] += value

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._values)


metrics = Metrics()
