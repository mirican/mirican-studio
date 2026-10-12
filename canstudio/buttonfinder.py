"""Sniffer — analiza sesji pulsów „trzymany przycisk" vs ramki CAN.

Wersja 2 (v0.9): analiza na poziomie BAJTÓW i BITÓW, empiryczne tło
(próbkowanie losowych okien) oraz ocena pewności kandydata.
"""

from __future__ import annotations

import math
import random
from bisect import bisect_left
from dataclasses import dataclass
from typing import Optional

EXT_MARK = 0x20000000


@dataclass
class ButtonHit:
    arbitration_id: int
    ext: bool
    key: int
    byte: int
    bit: Optional[int] = None
    hits: int = 0
    total: int = 0
    returns: int = 0
    delay_ms: Optional[float] = None
    delay_spread_ms: Optional[float] = None
    baseline: float = 0.0
    confidence: float = 0.0
    before: Optional[int] = None
    held: Optional[int] = None
    note: str = ""


def _series_with_changes(frames, getter):
    ts = [t for t, _ in frames]
    vals = [getter(d) for _, d in frames]
    changes = []
    for k in range(1, len(frames)):
        if vals[k] != vals[k - 1]:
            changes.append(ts[k])
    return ts, vals, changes


def _eval_series(ts, vals, changes, pairs, tol_s, pre_s):
    hits = rets = tot = 0
    delays = []
    before_v = held_v = None
    n = len(ts)
    for td, tu in pairs:
        i = bisect_left(ts, td - tol_s) - 1
        if i < 0:
            continue
        v_before = vals[i]
        a = bisect_left(ts, td + tol_s)
        b = bisect_left(ts, tu - tol_s)
        if b > a:
            v_held = vals[b - 1]
        else:
            mid = bisect_left(ts, (td + tu) / 2)
            if mid >= n:
                continue
            v_held = vals[mid]
        tot += 1
        if v_held != v_before:
            hits += 1
            before_v, held_v = v_before, v_held
            for tt in changes:
                if td - 0.25 <= tt <= td + 1.0:
                    delays.append((tt - td) * 1000.0)
                    break
        a1 = bisect_left(ts, tu + tol_s)
        a2 = bisect_left(ts, tu + pre_s) - 1
        if 0 <= a1 <= a2:
            if vals[a2] == v_before:
                rets += 1
    return hits, rets, tot, delays, before_v, held_v


def _empirical_baseline(ts, changes, pairs, rng, trials=180):
    """Jaki % losowych okien (tej samej długości) zawiera zmianę wartości."""
    if not pairs or not ts:
        return None
    win = sum(u - d for d, u in pairs) / len(pairs)
    span = (ts[-1] - ts[0]) - win
    if span <= win * 4:
        return None
    got = 0
    for _ in range(trials):
        t0 = ts[0] + rng.random() * span
        t1 = t0 + win
        a = bisect_left(changes, t0)
        if a < len(changes) and changes[a] <= t1:
            got += 1
    return got / trials


def find_button(messages, downs, ups, pre_s=2.0, tol_s=0.35, top=14):
    pairs = list(zip(sorted(downs), sorted(ups)))
    if not pairs or not messages:
        return []

    series: dict = {}
    for m in sorted(messages, key=lambda x: x.timestamp):
        key = m.arbitration_id + (EXT_MARK if m.is_extended_id else 0)
        series.setdefault(key, []).append((m.timestamp, bytes(m.data)))

    ts_all = [m.timestamp for m in messages]
    duration = max(1e-9, max(ts_all) - min(ts_all))
    win_avg = sum(u - d for d, u in pairs) / len(pairs)
    rng = random.Random(1234)

    results = []
    for key, frames in series.items():
        ext = key >= EXT_MARK
        aid = key - EXT_MARK if ext else key
        dlc = min(len(d) for _, d in frames)
        for i in range(dlc):
            candidates = []

            ts, vals, changes = _series_with_changes(frames, lambda d, i=i: d[i])
            h, r, tot, delays, bv, hv = _eval_series(ts, vals, changes, pairs, tol_s, pre_s)
            if tot and h:
                candidates.append(("byte", None, h, r, tot, delays, bv, hv, changes))

            for bit in range(8):
                getter = (lambda d, i=i, bit=bit: (d[i] >> bit) & 1)
                tsb, valsb, changesb = _series_with_changes(frames, getter)
                if len(changesb) >= len(changes):
                    continue  # bit nie wnosi nic nowego (bajt równie spokojny)
                hb, rb, totb, delaysb, bvb, hvb = _eval_series(
                    tsb, valsb, changesb, pairs, tol_s, pre_s)
                if totb and hb:
                    candidates.append(("bit", bit, hb, rb, totb, delaysb, bvb, hvb, changesb))

            for kind, bit, h, r, tot, delays, bv, hv, ch_list in candidates:
                lam = len(ch_list) * win_avg / duration
                base_model = 1 - math.exp(-lam) if lam > 0 else 0.0
                base_emp = _empirical_baseline(ts, ch_list, pairs, rng)
                baseline = max(base_model, base_emp) if base_emp is not None else base_model
                baseline = min(baseline, 0.99)
                delay = sum(delays) / len(delays) if delays else None
                spread = None
                if len(delays) >= 2 and delay is not None:
                    spread = (sum((x - delay) ** 2 for x in delays) / len(delays)) ** 0.5
                hit_frac = h / tot
                conf = hit_frac * (1 - baseline) + 0.2 * (r / tot)
                conf = max(0.0, min(1.0, conf))
                note = ""
                if h >= 2 and r >= h:
                    note = "chwilowy (wraca po puszczeniu)"
                elif h == tot and r == 0:
                    note = "stan trwały / zatrzask? (nie wraca)"
                results.append(ButtonHit(
                    arbitration_id=aid, ext=ext, key=key, byte=i, bit=bit,
                    hits=h, total=tot, returns=r,
                    delay_ms=(round(delay, 1) if delay is not None else None),
                    delay_spread_ms=(round(spread, 1) if spread is not None else None),
                    baseline=baseline, confidence=conf, before=bv, held=hv, note=note))

    results.sort(key=lambda x: (-(x.hits / x.total), -x.confidence))
    return results[:top]
