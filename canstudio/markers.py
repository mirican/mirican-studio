"""Znaczniki (markery) w logach + korelacja zdarzeń.

Znaczniki zapisujemy w logu jako linie komentarza::

    # MARK 1760000123.456 przycisk szyby

Dzięki temu można później automatycznie odpowiedzieć na pytanie:
"który bajt zmienia się krótko po wciśnięciu tego przycisku?".
"""

from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass

_MARK_RE = re.compile(r"^#\s*MARK\s+(?P<ts>[\d.]+)\s+(?P<label>.+?)\s*$")


@dataclass
class Marker:
    timestamp: float
    label: str


@dataclass
class Candidate:
    arbitration_id: int
    byte: int
    hits: int
    total: int
    baseline: float


def parse_marker_line(line: str):
    m = _MARK_RE.match(line.strip())
    if not m:
        return None
    return Marker(float(m.group("ts")), m.group("label"))


def read_candump_with_markers(path):
    """Czyta log candump; zwraca (lista wiadomości, lista znaczników)."""
    from .frames import message_from_frame, parse_frame_line

    messages, markers = [], []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                marker = parse_marker_line(line)
                if marker:
                    markers.append(marker)
                continue
            try:
                messages.append(message_from_frame(parse_frame_line(line)))
            except ValueError:
                continue
    return messages, markers


def correlate(messages, markers, window_s: float = 1.5, pre_s: float = 1.0, top: int = 10):
    """Dla każdej etykiety zwraca kandydatów (ID, bajt) zmieniających się w oknie
    po znaczniku.

    Zwraca ``{label: (liczba_znaczników, [Candidate, ...])}``.
    Kandydaci posortowani po (trafienia/całkowite) - tło.
    """
    series: dict = {}
    for m in sorted(messages, key=lambda x: x.timestamp):
        series.setdefault(m.arbitration_id, []).append((m.timestamp, bytes(m.data)))

    labels: dict = {}
    for marker in markers:
        labels.setdefault(marker.label, []).append(marker.timestamp)

    duration = 1.0
    all_ts = [m.timestamp for m in messages]
    if all_ts:
        duration = max(1e-9, max(all_ts) - min(all_ts))

    result = {}
    for label, times in labels.items():
        cands = []
        for aid, frames in series.items():
            if not frames:
                continue
            ts = [t for t, _ in frames]
            dlc = min(len(d) for _, d in frames)
            changes = [[] for _ in range(dlc)]
            for k in range(1, len(frames)):
                prev = frames[k - 1][1]
                cur = frames[k][1]
                t_cur = frames[k][0]
                for i in range(dlc):
                    if prev[i] != cur[i]:
                        changes[i].append(t_cur)
            for i in range(dlc):
                hits = 0
                total = 0
                for tm in times:
                    idx = bisect.bisect_left(ts, tm) - 1
                    if idx < 0:
                        continue
                    base = frames[idx][1]
                    if i >= len(base):
                        continue
                    total += 1
                    j = idx + 1
                    while j < len(frames) and frames[j][0] <= tm + window_s:
                        if frames[j][1][i] != base[i]:
                            hits += 1
                            break
                        j += 1
                if total == 0 or hits == 0:
                    continue
                lam = len(changes[i]) * window_s / duration
                baseline = 1 - math.exp(-lam) if lam > 0 else 0.0
                cands.append(Candidate(aid, i, hits, total, baseline))
        cands.sort(key=lambda c: (c.hits / c.total) - c.baseline, reverse=True)
        result[label] = (len(times), cands[:top])
    return result
