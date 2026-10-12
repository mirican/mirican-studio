# -*- coding: utf-8 -*-
"""Testy syntetyczne auto-DBC (generator .dbc z logu).

Uruchomienie:
    py tests/test_autodbc.py
"""

from __future__ import annotations

import io
import os
import sys
from argparse import Namespace
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import can  # noqa: E402

from canstudio import dbcgen  # noqa: E402
from canstudio.dbc import load_dbc  # noqa: E402
from canstudio.logio import write_candump  # noqa: E402
from canstudio.tools import autodbc  # noqa: E402

TESTS = []
LOG = os.path.join(ROOT, "logs", "_test_autodbc.log")
OUT_DBC = os.path.join(ROOT, "dbc", "auto__test_autodbc.dbc")


def test(fn):
    TESTS.append(fn)
    return fn


def make_frames():
    msgs = []
    t = 1000.0
    for i in range(80):
        # 0x130: b0 const, b1 licznik, b2 przełącznik (rzadko), b3..b6 zmienne, b7 xor-suma
        body = [0x03, i & 0xFF, 0x00, (i * 7) & 0xFF, (i * 13) & 0xFF,
                (i * 29) & 0xFF, 0x10, 0x00]
        if i in (40, 41, 42):
            body[2] = 0x01
        chk = 0
        for x in body[:7]:
            chk ^= x
        body[7] = chk
        m = can.Message(arbitration_id=0x130, data=bytes(body), is_extended_id=False)
        m.timestamp = t
        t += 0.02
        msgs.append(m)

    t = 1000.0
    for i in range(40):
        # 0x2CA: licznik + stałe
        m = can.Message(arbitration_id=0x2CA, data=bytes([i & 0xFF, 0xAA, 0xBB, 0xCC]),
                        is_extended_id=False)
        m.timestamp = t
        t += 0.05
        msgs.append(m)

    t = 1000.0
    for i in range(20):
        # 29-bit: 0x18DAF110, licznik + stałe
        m = can.Message(arbitration_id=0x18DAF110,
                        data=bytes([i & 0xFF, 0x62, 0x00, 0x42, 0x00, 0x00, 0x00, 0x00]),
                        is_extended_id=True)
        m.timestamp = t
        t += 0.1
        msgs.append(m)
    return msgs


def ns(**over):
    args = Namespace(log=LOG, capture=None, out=None, ids=None, top=24, min_frames=12,
                     interface=None, channel=None, bitrate=None, tty_baud=None,
                     silent=False, silent_mode="m1", fd=False, profile=None)
    for key, value in over.items():
        setattr(args, key, value)
    return args


def run_capture(args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = autodbc.run(args)
    return rc, buf.getvalue()


@test
def test_generate_and_load():
    write_candump(LOG, make_frames())
    rc, out = run_capture(ns())
    assert rc == 0, out
    assert os.path.exists(OUT_DBC), out

    db = load_dbc(OUT_DBC)
    names = sorted(m.name for m in db.messages)
    assert "MSG_130" in names and "MSG_2CA" in names and "MSG_18DAF110" in names, names

    frames = make_frames()
    f130 = bytes(frames[10].data)
    dec = db.decode_message(0x130, f130)
    assert dec["b0_const"] == 3, dec
    assert dec["b1_counter"] == 10, dec
    assert "b7_checksum" in dec, dec

    fext = bytes(frames[-1].data)
    de = db.decode_message(0x18DAF110, fext)
    assert de["b0_counter"] == 19, de

    with open(OUT_DBC, encoding="utf-8") as fh:
        txt = fh.read()
    assert "b1_counter" in txt and "b7_checksum" in txt and "b2_switch" in txt, txt[:500]
    assert "class: counter" in txt
    assert "period~" in txt


@test
def test_ids_filter():
    rc, out = run_capture(ns(ids="0x130"))
    assert rc == 0, out
    db = load_dbc(OUT_DBC)
    names = [m.name for m in db.messages]
    assert names == ["MSG_130"], names


@test
def test_signal_span():
    import cantools

    from canstudio.dbc import signal_map

    txt = ('VERSION "t"\n\nNS_ :\n\tCM_\n\nBS_:\n\nBU_: Vector__XXX\n\n'
           'BO_ 304 MSG: 8 Vector__XXX\n'
           ' SG_ Be16 : 23|16@0+ (1,0) [0|65535] "" Vector__XXX\n'
           ' SG_ BeTop : 7|8@0+ (1,0) [0|255] "" Vector__XXX\n'
           'BO_ 305 MSG2: 8 Vector__XXX\n'
           ' SG_ Le16 : 16|16@1+ (1,0) [0|65535] "" Vector__XXX\n'
           ' SG_ LeTail : 32|8@1+ (1,0) [0|255] "" Vector__XXX\n')
    db = cantools.database.load_string(txt, database_format="dbc")
    m = signal_map(db, 0x130)
    by = {s["name"]: s for s in m["signals"]}
    assert by["Be16"]["bytes"] == [2, 3], by["Be16"]
    assert by["BeTop"]["bytes"] == [0], by["BeTop"]
    m2 = signal_map(db, 0x131)
    by2 = {s["name"]: s for s in m2["signals"]}
    assert by2["Le16"]["bytes"] == [2, 3], by2["Le16"]
    assert by2["LeTail"]["bytes"] == [4], by2["LeTail"]
    val = db.decode_message(0x130, bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]))
    assert hex(val["Be16"]) == "0x3344", val


@test
def test_empty_raises():
    try:
        dbcgen.build_dbc([])
    except ValueError:
        return
    raise AssertionError("oczekiwano ValueError dla pustej listy")


def main() -> int:
    fails = 0
    print(f"# miriCAN Studio - testy auto-DBC ({len(TESTS)} testów)")
    try:
        for fn in TESTS:
            try:
                fn()
                print(f"  PASS  {fn.__name__}")
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print(f"  FAIL  {fn.__name__}: {type(exc).__name__}: {exc}")
    finally:
        for path in (LOG, OUT_DBC):
            try:
                os.remove(path)
            except OSError:
                pass
    total = len(TESTS)
    print(f"# wynik: {total - fails}/{total} OK")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
