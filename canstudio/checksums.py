"""Detekcja liczników oraz sum kontrolnych w ramkach jednego ID.

Heurystyki:
* licznik  - bajt (lub nibble) rośnie o 1 między kolejnymi ramkami,
* suma     - bajt równy wynikowi jednego z typowych algorytmów (XOR/SUM/CRC8)
             policzonemu po pozostałych bajtach ramki.

Wynik służy do przygotowania wiarygodnego odtworzania (replay/TX) ramek.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Sequence

COUNTER_THRESHOLD = 0.90
CHECKSUM_THRESHOLD = 0.95
CHECKSUM_REPORT_THRESHOLD = 0.80
MIN_FRAMES = 12


# --- kalkulatory -------------------------------------------------------------

def xor_all(data: bytes) -> int:
    acc = 0
    for b in data:
        acc ^= b
    return acc


def sum8(data: bytes) -> int:
    return sum(data) & 0xFF


def crc8(data: bytes, poly: int, init: int = 0x00, xorout: int = 0x00) -> int:
    crc = init
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc ^ xorout


ALGORITHMS = [
    ("xor8", xor_all),
    ("xor8 ^ FF", lambda d: xor_all(d) ^ 0xFF),
    ("sum8", sum8),
    ("sum8 ^ FF", lambda d: (~sum8(d)) & 0xFF),
    ("crc8 (J1850: 1D/FF/FF)", lambda d: crc8(d, 0x1D, 0xFF, 0xFF)),
    ("crc8 (H2F: 2F/FF/FF)", lambda d: crc8(d, 0x2F, 0xFF, 0xFF)),
    ("crc8 (1D/00/00)", lambda d: crc8(d, 0x1D, 0x00, 0x00)),
]


# --- wyniki ------------------------------------------------------------------

@dataclass
class CounterHit:
    byte: int
    kind: str
    score: float


@dataclass
class ChecksumHit:
    byte: int
    algo: str
    score: float


@dataclass
class AnalysisResult:
    count: int
    dlc: int
    counters: list = field(default_factory=list)
    checksums: list = field(default_factory=list)        # >= CHECKSUM_THRESHOLD
    weak_checksums: list = field(default_factory=list)   # 0.8 .. próg


# --- detekcja ----------------------------------------------------------------

def _frac_delta_one(values, modulo: int) -> float:
    if len(values) < 2:
        return 0.0
    hits = 0
    for a, b in zip(values, values[1:]):
        if ((b - a) % modulo) == 1:
            hits += 1
    return hits / (len(values) - 1)


def analyze_frames(frames: Sequence[bytes]) -> AnalysisResult:
    frames = [bytes(f) for f in frames if len(f) >= 2]
    if not frames:
        return AnalysisResult(0, 0)
    dlc = Counter(len(f) for f in frames).most_common(1)[0][0]
    frames = [f for f in frames if len(f) == dlc]
    n = len(frames)
    result = AnalysisResult(count=n, dlc=dlc)
    if n < MIN_FRAMES:
        return result

    counter_bytes = set()
    for i in range(dlc):
        col = [f[i] for f in frames]
        best = None
        for kind, modulo, getter in (
            ("cały bajt +1", 256, lambda b: b),
            ("dolny nibble +1", 16, lambda b: b & 0x0F),
            ("górny nibble +1", 16, lambda b: (b >> 4) & 0x0F),
        ):
            frac = _frac_delta_one([getter(v) for v in col], modulo)
            if best is None or frac > best[2]:
                best = (kind, i, frac)
        if best and best[2] >= COUNTER_THRESHOLD:
            result.counters.append(CounterHit(byte=best[1], kind=best[0], score=best[2]))
            counter_bytes.add(best[1])

    # Uwaga: XOR ma własność sprawiającą, że gdy xor całej ramki == 0,
    # XOR-owa suma "pasuje" jednocześnie na KAŻDEJ pozycji (algebra).
    # Dlatego XOR sprawdzamy raz, globalnie, a nie per bajt.
    frac_xor0 = sum(1 for f in frames if xor_all(f) == 0x00) / n
    frac_xorff = sum(1 for f in frames if xor_all(f) == 0xFF) / n
    if frac_xor0 >= CHECKSUM_THRESHOLD:
        result.checksums.append(ChecksumHit(
            byte=-1, algo="xor8 (cała ramka = 0, typowo ostatni bajt)", score=frac_xor0))
    elif frac_xor0 >= CHECKSUM_REPORT_THRESHOLD:
        result.weak_checksums.append(ChecksumHit(
            byte=-1, algo="xor8 (cała ramka = 0)", score=frac_xor0))
    if frac_xorff >= CHECKSUM_THRESHOLD:
        result.checksums.append(ChecksumHit(
            byte=-1, algo="xor8 ^ FF (cała ramka = FF, typowo ostatni bajt)", score=frac_xorff))
    elif frac_xorff >= CHECKSUM_REPORT_THRESHOLD:
        result.weak_checksums.append(ChecksumHit(
            byte=-1, algo="xor8 ^ FF (cała ramka = FF)", score=frac_xorff))

    per_byte_algos = [(name, algo) for name, algo in ALGORITHMS
                      if not name.startswith("xor8")]
    for c in range(dlc):
        if c in counter_bytes:
            continue
        variants = [[f[i] for i in range(dlc) if i != c] for f in frames]
        for name, algo in per_byte_algos:
            hits = 0
            for vals, f in zip(variants, frames):
                try:
                    if algo(bytes(vals)) == f[c]:
                        hits += 1
                except Exception:
                    pass
            frac = hits / n
            if frac >= CHECKSUM_THRESHOLD:
                result.checksums.append(ChecksumHit(byte=c, algo=name, score=frac))
            elif frac >= CHECKSUM_REPORT_THRESHOLD:
                result.weak_checksums.append(ChecksumHit(byte=c, algo=name, score=frac))

    result.checksums.sort(key=lambda h: (-h.score, h.byte))
    result.weak_checksums.sort(key=lambda h: (-h.score, h.byte))
    return result


def compute(algo_name: str, data_without_byte: bytes) -> int:
    """Liczy sumę wybranym algorytmem (do przyszłej wysyłki ramek)."""
    for name, algo in ALGORITHMS:
        if name == algo_name:
            return algo(bytes(data_without_byte))
    raise KeyError(f"Nieznany algorytm: {algo_name}")
