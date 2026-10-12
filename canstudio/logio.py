"""Odczyt i zapis logów CAN (candump, .asc, .blf)."""

from __future__ import annotations

from pathlib import Path

import can

from .frames import parse_frame_line, message_from_frame, format_frame


def read_log(path) -> list:
    """Wczytuje log; format rozpoznawany po rozszerzeniu.

    * ``.blf`` - Python-can BLFReader (tylko odczyt),
    * ``.asc`` - Vector ASCII (Vector/PCAN-View/SavvyCAN),
    * pozostałe (``.log``, ``.txt``) - candump / candump -L.
    """
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".blf":
        with can.BLFReader(str(p)) as reader:
            return list(reader)
    if ext == ".asc":
        with can.ASCReader(str(p)) as reader:
            return list(reader)

    messages = []
    with open(p, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                frame = parse_frame_line(line)
            except ValueError:
                continue  # pomijamy linie, które nie są ramkami
            messages.append(message_from_frame(frame))
    return messages


def write_candump(path, messages) -> int:
    """Zapisuje ramki w formacie candump -L. Zwraca liczbę zapisanych."""
    n = 0
    with open(path, "w", encoding="utf-8", buffering=1) as fh:
        for m in messages:
            channel = getattr(m, "channel", None) or "can0"
            fh.write(format_frame(m, str(channel)) + "\n")
            n += 1
    return n


def trim_messages(messages, *, from_s=None, to_s=None, offset=0, count=0):
    """Wycina fragment logu.

    ``from_s`` / ``to_s`` - zakres czasu w sekundach (od pierwszej ramki);
    ``offset`` / ``count`` - dodatkowo odrzuć N początkowych i zostaw co najwyżej M.
    """
    if not messages:
        return []
    t0 = messages[0].timestamp or 0.0
    selected = []
    eps = 1e-9  # tolerancja float (np. 0.1*k)
    for m in messages:
        ts = (m.timestamp or t0) - t0
        if from_s is not None and ts < from_s - eps:
            continue
        if to_s is not None and ts > to_s + eps:
            break
        selected.append(m)
    if offset:
        selected = selected[offset:]
    if count:
        selected = selected[:count]
    return selected


def write_asc(path, messages) -> int:
    """Zapisuje ramki w formacie Vector ASCII (.asc)."""
    writer = can.ASCWriter(str(path))
    n = 0
    try:
        for m in messages:
            writer.on_message_received(m)
            n += 1
    finally:
        writer.stop()
    return n
