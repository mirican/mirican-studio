"""Porównywanie nagrań CAN: co zmieniło się między dwoma logami."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class ByteDiff:
    byte: int
    mean_a: float
    mean_b: float
    values_a: list
    values_b: list
    score: float
    note: str = ""


@dataclass
class IdDiff:
    arbitration_id: int
    n_a: int
    n_b: int
    score: float
    bytes: list = field(default_factory=list)


def _top(values, k: int = 3):
    return [v for v, _ in Counter(values).most_common(k)]


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def _group(messages):
    groups: dict = {}
    for m in messages:
        groups.setdefault(m.arbitration_id, []).append(bytes(m.data))
    return groups


def diff_logs(messages_a, messages_b, min_frames: int = 10,
              per_id_bytes: int = 6, top_ids: int = 10):
    """Porównuje dwa zbiory ramek.

    Zwraca ``(diffs, only)``:
    * ``diffs`` - lista ``IdDiff`` dla ID obecnych w obu logach (posortowana
      po sile zmian),
    * ``only``  - {"A": [(id, count), ...], "B": [...]} dla ID obecnych tylko
      w jednym z logów.
    """
    ga, gb = _group(messages_a), _group(messages_b)
    diffs = []
    only = {"A": [], "B": []}

    for aid in sorted(set(ga) | set(gb)):
        fa, fb = ga.get(aid, []), gb.get(aid, [])
        if not fa:
            only["B"].append((aid, len(fb)))
            continue
        if not fb:
            only["A"].append((aid, len(fa)))
            continue
        if len(fa) < min_frames or len(fb) < min_frames:
            continue

        dlc = min(len(fa[0]), len(fb[0]), min(len(x) for x in fa), min(len(x) for x in fb))
        byte_diffs = []
        for i in range(dlc):
            va = [x[i] for x in fa]
            vb = [x[i] for x in fb]
            score = abs(_mean(va) - _mean(vb))
            sa, sb = set(va), set(vb)
            score += 64 * (len(sb - sa) / max(1, len(sb)))  # nowe wartości w B
            note = ""
            if len(sa) == 1 and len(sb) > 1:
                note = "stały w A, zmienny w B"
            elif len(sa) > 1 and len(sb) == 1:
                note = "zmienny w A, stały w B"
            if score >= 1.0:
                byte_diffs.append(ByteDiff(i, _mean(va), _mean(vb), _top(va), _top(vb), score, note))

        byte_diffs.sort(key=lambda d: d.score, reverse=True)
        id_score = sum(d.score for d in byte_diffs[:3])
        if byte_diffs or id_score > 0:
            diffs.append(IdDiff(aid, len(fa), len(fb), id_score, byte_diffs[:per_id_bytes]))

    diffs.sort(key=lambda d: d.score, reverse=True)
    only["A"].sort(key=lambda t: t[1], reverse=True)
    only["B"].sort(key=lambda t: t[1], reverse=True)
    return diffs[:top_ids], only
