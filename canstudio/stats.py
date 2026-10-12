"""Statystyki sesji: zliczanie, okresy ramek, ostatnie dane."""

from __future__ import annotations

from collections import deque


def estimate_period(timestamps):
    """Mediana odstępów między kolejnymi znacznikami czasu (albo None)."""
    times = list(timestamps)
    if len(times) < 2:
        return None
    deltas = sorted(b - a for a, b in zip(times, times[1:]))
    mid = len(deltas) // 2
    return deltas[mid] if len(deltas) % 2 else (deltas[mid - 1] + deltas[mid]) / 2


class IdStats:
    """Zliczanie ramek per ID (+ okres, ostatnie dane, historia czasów)."""

    def __init__(self, history: int = 300) -> None:
        self.counts: dict = {}
        self.total = 0
        self._times: dict = {}
        self._last: dict = {}
        self._history = history

    def add(self, arbitration_id: int, timestamp=None, data=None) -> None:
        self.counts[arbitration_id] = self.counts.get(arbitration_id, 0) + 1
        self.total += 1
        if timestamp is not None:
            dq = self._times.get(arbitration_id)
            if dq is None:
                dq = self._times[arbitration_id] = deque(maxlen=self._history)
            dq.append(timestamp)
        if data is not None:
            self._last[arbitration_id] = bytes(data)

    def top(self, n: int = 10):
        return sorted(self.counts.items(), key=lambda kv: kv[1], reverse=True)[:n]

    def period(self, arbitration_id: int):
        """Estymata okresu ramki (mediana odstępów) w sekundach lub None."""
        dq = self._times.get(arbitration_id)
        return estimate_period(dq) if dq else None

    def last(self, arbitration_id: int):
        return self._last.get(arbitration_id)


def group_bytes_by_id(messages, limit_per_id: int = 0):
    """Zwraca dict: arb_id -> [bajty ramek] (w kolejności wystąpienia).

    ``limit_per_id`` > 0 ogranicza liczbę przechowywanych ramek na ID
    (przydatne dla bardzo dużych logów).
    """
    groups: dict = {}
    for m in messages:
        bucket = groups.setdefault(m.arbitration_id, [])
        if not limit_per_id or len(bucket) < limit_per_id:
            bucket.append(bytes(m.data))
    return groups
