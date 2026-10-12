# -*- coding: utf-8 -*-
"""Testy procedur: reassembly ISO-TP z logu + kompilacja kroków + magazyn."""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import can  # noqa: E402

from canstudio.isotp_log import find_sessions, payloads_per_id, slice_by_window  # noqa: E402
from canstudio.logio import read_log, write_candump  # noqa: E402
from canstudio.procedures import (compile_procedure, delete_procedure,  # noqa: E402
                                  list_procedures, load_procedure, save_procedure)

TESTS = []
LOG = os.path.join(ROOT, "logs", "_test_proc.log")
REQ, RESP = 0x6F1, 0x6F9


def test(fn):
    TESTS.append(fn)
    return fn


def sf(p: bytes) -> bytes:
    return bytes([len(p)]) + p + b"\x00" * (7 - len(p))


def mf(p: bytes) -> list:
    """Payload → ramki FF+CF (bez FC)."""
    n = len(p)
    frames = [bytes([0x10 | (n >> 8), n & 0xFF]) + p[:6]]
    rest, i = p[6:], 1
    while rest:
        chunk, rest = rest[:7], rest[7:]
        frames.append(bytes([0x20 | (i & 0x0F)]) + chunk)
        i += 1
    return frames


def build_msgs():
    msgs, t = [], [1.0]

    def send(aid, data):
        m = can.Message(arbitration_id=aid, is_extended_id=False, data=data)
        m.timestamp = t[0]
        msgs.append(m)

    def adv(dt):
        t[0] += dt

    send(REQ, sf(b"\x3e\x00")); adv(0.01); send(RESP, sf(b"\x7e\x00")); adv(1.0)
    send(REQ, sf(b"\x3e\x00")); adv(0.01); send(RESP, sf(b"\x7e\x00")); adv(0.2)
    send(REQ, sf(b"\x10\x03")); adv(0.02); send(RESP, sf(b"\x50\x03\x00\x32\x01\xf4")); adv(0.2)
    send(REQ, sf(b"\x31\x01\x02\x03")); adv(0.02); send(RESP, sf(b"\x7f\x31\x78")); adv(0.05)
    send(RESP, sf(b"\x71\x01\x02\x03\xde\xad")); adv(0.2)
    send(REQ, sf(b"\x22\xf1\x90")); adv(0.005)
    send(REQ, b"\x30\x00\x00")  # FC testera (pomijane) — nie na RESP
    adv(0.005)
    for f in mf(b"\x62\xf1\x90WBA5E510X0G123456"):
        send(RESP, f); adv(0.005)
    adv(0.2)
    send(REQ, sf(b"\x27\x01")); adv(0.02); send(RESP, sf(b"\x67\x01\xde\xad\xbe\xef")); adv(0.2)
    send(REQ, sf(b"\x27\x02\x11\x22\x33\x44")); adv(0.02); send(RESP, sf(b"\x67\x02")); adv(0.2)
    return msgs


@test
def test_reassembly_and_sessions():
    write_candump(LOG, build_msgs())
    messages = read_log(LOG)
    assert messages, "log pusty po round-trip"
    events, ext = payloads_per_id(messages)
    assert REQ in events and RESP in events, list(events.keys())
    vin_events = [p for _, p in events[RESP] if p[:3] == b"\x62\xf1\x90"]
    assert len(vin_events) == 1 and len(vin_events[0]) == 20, vin_events

    sessions = find_sessions(events, ext, offset=8, min_exchanges=1)
    assert sessions, "nie znaleziono sesji"
    s = sessions[0]
    assert (s.req_id, s.resp_id) == (REQ, RESP), (s.req_id, s.resp_id)
    assert len(s.exchanges) == 7, len(s.exchanges)
    routine = [e for e in s.exchanges if e.req == b"\x31\x01\x02\x03"][0]
    assert routine.pendings == 1 and routine.resp == b"\x71\x01\x02\x03\xde\xad"
    # okno czasowe (względem pierwszej ramki)
    sliced = slice_by_window(messages, from_s=0.5, to_s=3.0)
    assert 0 < len(sliced) < len(messages)


@test
def test_compile_steps():
    messages = read_log(LOG)
    events, ext = payloads_per_id(messages)
    s = find_sessions(events, ext, offset=8, min_exchanges=1)[0]
    proc = compile_procedure(s, name="Procedura testowa", vehicle="Test")
    steps = proc["steps"]
    assert len(steps) == 5, [st["send"] for st in steps]
    assert steps[0]["send"] == "10 03" and steps[0]["expect"] == "50 03 00 32 01 F4"
    assert steps[1]["send"] == "31 01 02 03" and steps[1]["pendings"] == 1
    assert steps[1]["expect"].startswith("71 01 02 03")
    vin_step = [st for st in steps if st["send"] == "22 F1 90"][0]
    assert vin_step["expect"].startswith("62 F1 90 57 42 41"), vin_step["expect"]
    assert proc["security"]["detected"] is True
    pairs = proc["security"]["pairs"]
    assert pairs and pairs[0]["seed"] == "DE AD BE EF" and pairs[0]["key"] == "11 22 33 44", pairs
    assert all(st["timeout_ms"] >= 200 for st in steps)


@test
def test_store_roundtrip():
    messages = read_log(LOG)
    events, ext = payloads_per_id(messages)
    s = find_sessions(events, ext, offset=8, min_exchanges=1)[0]
    proc = compile_procedure(s, name="Test Olej F30")
    path = save_procedure(proc)
    assert path.exists()
    try:
        items = list_procedures()
        assert any(i["id"] == proc["id"] for i in items), items
        loaded = load_procedure(proc["id"])
        assert loaded["name"] == "Test Olej F30" and len(loaded["steps"]) == 5
        assert loaded["format"] == "mirican-procedure/1"
    finally:
        delete_procedure(proc["id"])
    assert not any(i["id"] == proc["id"] for i in list_procedures())


def main() -> int:
    fails = 0
    print(f"# miriCAN Studio - testy procedur ({len(TESTS)} testów)")
    try:
        for fn in TESTS:
            try:
                fn()
                print(f"  PASS  {fn.__name__}")
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print(f"  FAIL  {fn.__name__}: {type(exc).__name__}: {exc}")
    finally:
        try:
            os.remove(LOG)
        except OSError:
            pass
    total = len(TESTS)
    print(f"# wynik: {total - fails}/{total} OK")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
