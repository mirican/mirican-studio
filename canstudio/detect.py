"""Automatyczna detekcja zmian i klasyfikacja bajtów (rdzeń automatyzacji).

* ``ChangeDetector`` - śledzi strumień na żywo i raportuje tylko "interesujące"
  zmiany: bajt stabilny od dłuższego czasu zmienia wartość (typowy objaw
  wciśniętego przycisku, flagi, zdarzenia).
* ``classify_frames`` - offline klasyfikacja bajtów w logu:
  stały / licznik / suma kontrolna / przełącznik / sensor.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from .checksums import analyze_frames


@dataclass
class ChangeEvent:
    arbitration_id: int
    byte: int            # -1 = nowe ID
    old: int
    new: int
    stable_frames: int
    changes_total: int


class ChangeDetector:
    """Raportuje zmiany bajtów, które wcześniej były stabilne."""

    def __init__(self, min_stable: int = 20, min_gap_s: float = 0.15):
        self.min_stable = min_stable
        self.min_gap_s = min_gap_s
        self._ids: dict = {}

    def feed(self, arbitration_id: int, data: bytes, t: float) -> list:
        state = self._ids.get(arbitration_id)
        if state is None:
            self._ids[arbitration_id] = {
                "bytes": [self._new_byte_state(b) for b in data],
                "frames": 1,
            }
            return [ChangeEvent(arbitration_id, -1, -1, -1, 0, 0)]

        events = []
        state["frames"] += 1
        states = state["bytes"]
        if len(states) != len(data):
            state["bytes"] = [self._new_byte_state(b) for b in data]
            return events

        for i, value in enumerate(data):
            st = states[i]
            st["frames"] += 1
            if value == st["last"]:
                st["stable"] += 1
                continue
            # zmiana wartości
            report = st["stable"] >= self.min_stable and (t - st["last_report"]) >= self.min_gap_s
            if report:
                events.append(ChangeEvent(arbitration_id, i, st["last"], value,
                                          st["stable"], st["changes"] + 1))
                st["last_report"] = t
            st["last"] = value
            st["stable"] = 0
            st["changes"] += 1
        return events

    @staticmethod
    def _new_byte_state(value: int) -> dict:
        return {"last": value, "stable": 0, "changes": 0, "frames": 1, "last_report": 0.0}

    def interesting_bytes(self, top: int = 15):
        """Bajty najbardziej 'zdarzeniowe' (rzadkie zmiany przy dużej liczbie ramek)."""
        rows = []
        for aid, state in self._ids.items():
            for i, st in enumerate(state["bytes"]):
                if st["changes"] and st["frames"]:
                    rate = st["changes"] / st["frames"]
                    if rate < 0.5:
                        rows.append((aid, i, st["changes"], st["frames"], rate))
        rows.sort(key=lambda r: (r[4], -r[2]))
        return rows[:top]


# ---------------------------------------------------------------------------
# Klasyfikacja offline
# ---------------------------------------------------------------------------

@dataclass
class ByteClass:
    byte: int
    kind: str
    detail: str


def classify_frames(frames: Sequence[bytes]) -> list:
    """Klasyfikuje każdy bajt: stały / licznik / suma / przełącznik / sensor."""
    frames = [bytes(f) for f in frames if len(f) >= 2]
    if not frames:
        return []
    dlc = Counter(len(f) for f in frames).most_common(1)[0][0]
    frames = [f for f in frames if len(f) == dlc]
    n = len(frames)

    checks = analyze_frames(frames)
    counter_map = {c.byte: c for c in checks.counters}
    checksum_bytes = {h.byte: h for h in checks.checksums if h.byte >= 0}
    global_checksums = [h for h in checks.checksums if h.byte < 0]

    classes = []
    for i in range(dlc):
        values = [f[i] for f in frames]
        distinct = len(set(values))
        changes = sum(1 for a, b in zip(values, values[1:]) if a != b)
        rate = changes / max(1, n - 1)

        if i in counter_map:
            classes.append(ByteClass(i, "licznik", counter_map[i].kind))
        elif i in checksum_bytes:
            classes.append(ByteClass(i, "suma", checksum_bytes[i].algo))
        elif global_checksums and i == dlc - 1:
            classes.append(ByteClass(i, "suma", global_checksums[0].algo))
        elif distinct == 1:
            classes.append(ByteClass(i, "stały", f"0x{values[0]:02X}"))
        elif distinct <= 4 and rate < 0.35:
            shown = ", ".join(f"0x{v:02X}" for v in sorted(set(values))[:4])
            note = f", zmian {changes}"
            if changes <= 3:
                note = f" (RZADKIE ZDARZENIE: {changes} zm.)"
            classes.append(ByteClass(i, "przełącznik/zdarzenie", f"[{shown}]{note}"))
        elif rate > 0.5 and distinct > 8:
            classes.append(ByteClass(i, "sensor", f"zakres {min(values)}–{max(values)}, zmian {changes}"))
        elif rate > 0.5:
            classes.append(ByteClass(i, "zmienny", f"mały zakres, różnych {distinct}, zmian {changes}"))
        else:
            classes.append(ByteClass(i, "mieszany", f"różnych {distinct}, zmian {changes}"))
    return classes
