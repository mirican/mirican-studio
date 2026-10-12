"""Dekodowanie ramek według plików DBC (cantools) + mapowanie sygnałów na bajty."""

from __future__ import annotations

import can


def load_dbc(path: str):
    """Ładuje plik DBC (także KCD/ARXML - patrz cantools).

    Najpierw próbuje tryb ścisły; gdy realna baza jest „krzywa” (nakładające się
    sygnały itp.), ponawia w trybie luźnym (`strict=False`) — dzięki temu wczytuje
    się większość produkcyjnych DBC z sieci.
    """
    import cantools
    try:
        return cantools.database.load_file(str(path))
    except Exception:
        return cantools.database.load_file(str(path), strict=False)


def decode_into(db, msg: can.Message):
    """Dekoduje ramkę według bazy; zwraca dict lub None, gdy nie pasuje."""
    try:
        return db.decode_message(msg.arbitration_id, bytes(msg.data))
    except Exception:
        return None


def signal_byte_span(sig) -> list:
    """Indeksy bajtów ramki obejmowanych przez sygnał DBC.

    * ``little_endian`` (Intel, @1): start = bit LSB sygnału (rośnie w górę),
    * ``big_endian`` (Motorola, @0): start = indeks sawtooth bitu MSB;
      numeracja sieciowa: ``8*(s//8) + (7 - s%8)``.

    Konwencja zweryfikowana empirycznie z cantools (dekodowanie 1:1).
    """
    start, length = int(sig.start), int(sig.length)
    if sig.byte_order == "little_endian":
        first, last = start // 8, (start + length - 1) // 8
    else:  # big_endian
        seq = 8 * (start // 8) + (7 - start % 8)
        first, last = seq // 8, (seq + length - 1) // 8
    return list(range(first, last + 1))


def signal_map(db, frame_id: int) -> dict:
    """Sygnały wiadomości o danym ID + ich pokrycie bajtów (do wiązania z klasyfikacją)."""
    msg = db.get_message_by_frame_id(frame_id)
    signals = []
    for s in msg.signals:
        bytes_ = signal_byte_span(s)
        signals.append({
            "name": s.name,
            "first": bytes_[0],
            "last": bytes_[-1],
            "bytes": bytes_,
            "unit": s.unit or "",
        })
    return {"name": msg.name, "length": msg.length, "signals": signals}
