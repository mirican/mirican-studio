"""Reassembly ISO-TP z logu CAN — na potrzeby kompilatora procedur.

Zamienia log (candump itd.) na strumienie „payloadów” ISO-TP per CAN ID
(scalanie Single Frame / First Frame + Consecutive Frames) i pozwala dopasować
pary żądanie→odpowiedź (typowo tester ↔ ECU).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Exchange:
    t: float
    req: bytes
    resp: bytes | None = None
    resp_t: float | None = None
    pendings: int = 0  # ile razy ECU odpowiedział 7F .. 78 (responsePending)


@dataclass
class Session:
    req_id: int
    resp_id: int
    ext: bool
    exchanges: list = field(default_factory=list)


def payloads_per_id(messages):
    """Zwraca (events_by_id, ext_by_id).

    ``events_by_id[can_id]`` = lista ``(t, payload)`` po reassembly ISO-TP
    (bez ramek Flow Control; niepełne sekwencje wielo-ramkowe są pomijane).
    """
    streams: dict = {}
    ext_map: dict = {}
    for m in messages:
        data = bytes(m.data)
        if not data:
            continue
        streams.setdefault(m.arbitration_id, []).append((m.timestamp or 0.0, data))
        ext_map[m.arbitration_id] = bool(getattr(m, "is_extended_id", False))

    events_by_id: dict = {}
    for aid, frames in streams.items():
        events = []
        pending = None  # {"left": int, "blob": bytearray, "t": float}
        for t, data in frames:
            pci = data[0] & 0xF0
            if pci == 0x00:  # Single Frame
                ln = data[0] & 0x0F
                if 0 < ln <= 7 and len(data) >= 1 + ln:
                    events.append((t, bytes(data[1:1 + ln])))
            elif pci == 0x10:  # First Frame
                ln = ((data[0] & 0x0F) << 8) | (data[1] if len(data) > 1 else 0)
                if ln == 0 and len(data) >= 8:  # extended length
                    ln = (data[2] << 8) | data[3]
                    blob = bytearray(data[4:])
                else:
                    blob = bytearray(data[2:])
                pending = {"left": ln, "blob": blob, "t": t}
            elif pci == 0x20:  # Consecutive Frame
                if pending is not None:
                    pending["blob"] += data[1:]
                    if len(pending["blob"]) >= pending["left"]:
                        events.append((pending["t"], bytes(pending["blob"][:pending["left"]])))
                        pending = None
            # 0x30 Flow Control — pomijamy
        if events:
            events_by_id[aid] = events
    return events_by_id, ext_map


def find_sessions(events_by_id, ext_by_id=None, *, offset: int = 8,
                  only_req_ids=None, max_gap_s: float = 10.0,
                  min_exchanges: int = 1):
    """Paruje kanały (req_id → resp_id = req_id + offset) w sesje z wymianami.

    Dla każdego żądania szuka pierwszej odpowiedzi po nim (w oknie ``max_gap_s``),
    pomijając odpowiedzi ``7F xx 78`` (responsePending) — ich licznik trafia
    do wymiany.
    """
    ext_by_id = ext_by_id or {}
    sessions = []
    for req_id in sorted(events_by_id.keys()):
        if only_req_ids is not None and req_id not in only_req_ids:
            continue
        resp_id = req_id + offset
        if resp_id not in events_by_id:
            continue
        req_events = events_by_id[req_id]
        resp_events = events_by_id[resp_id]
        exchanges = []
        matched = 0
        ri = 0
        for t, req in req_events:
            while ri < len(resp_events) and resp_events[ri][0] < t:
                ri += 1
            if ri >= len(resp_events) or resp_events[ri][0] > t + max_gap_s:
                exchanges.append(Exchange(t=float(t), req=req))
                continue
            resp_t, resp = resp_events[ri]
            ri += 1
            pend = 0
            while (len(resp) >= 3 and resp[0] == 0x7F and resp[2] == 0x78
                   and ri < len(resp_events) and resp_events[ri][0] <= t + max_gap_s):
                pend += 1
                resp_t, resp = resp_events[ri]
                ri += 1
            exchanges.append(Exchange(t=float(t), req=req, resp=resp,
                                      resp_t=float(resp_t), pendings=pend))
            matched += 1
        if exchanges and matched >= min_exchanges:
            sessions.append(Session(req_id=req_id, resp_id=resp_id,
                                    ext=bool(ext_by_id.get(req_id, False)),
                                    exchanges=exchanges))
    sessions.sort(key=lambda s: len(s.exchanges), reverse=True)
    return sessions


def slice_by_window(messages, from_s=None, to_s=None):
    """Wycina log po czasie względem pierwszej ramki (dla okna nagrania)."""
    if not messages:
        return []
    t0 = messages[0].timestamp or 0.0
    out = []
    for m in messages:
        ts = (m.timestamp or t0) - t0
        if from_s is not None and ts < from_s - 1e-9:
            continue
        if to_s is not None and ts > to_s + 1e-9:
            break
        out.append(m)
    return out
