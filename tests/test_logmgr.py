# -*- coding: utf-8 -*-
"""Testy menedżera logów: przycinanie + odtwarzanie z modyfikacją (wirtualna magistrala).

Uruchomienie:
    py tests/test_logmgr.py
"""

from __future__ import annotations

import io
import os
import sys
import threading
import time
from argparse import Namespace
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import can  # noqa: E402

from canstudio.logio import trim_messages, write_candump  # noqa: E402
from canstudio.tools import replay as replay_tool  # noqa: E402

TESTS = []
LOG = os.path.join(ROOT, "logs", "_test_logmgr.log")
CH = "lgtool-test"


def test(fn):
    TESTS.append(fn)
    return fn


def make_msgs():
    msgs = []
    for i in range(100):
        m = can.Message(arbitration_id=0x130, is_extended_id=False,
                        data=bytes([i & 0xFF, i & 0xFF, 0x10, 0x00, 0x80, 0x00, 0x00, 0x00]))
        m.timestamp = 100.0 + i * 0.1
        msgs.append(m)
    return msgs


@test
def test_trim_time_and_count():
    msgs = make_msgs()
    sel = trim_messages(msgs, from_s=2.0, to_s=5.0)
    assert len(sel) == 31, len(sel)
    assert sel[0].timestamp >= 102.0 and sel[-1].timestamp <= 105.0
    sel2 = trim_messages(msgs, from_s=1.0, offset=10, count=5)
    assert len(sel2) == 5, len(sel2)
    assert abs(sel2[0].timestamp - 102.0) < 1e-6, sel2[0].timestamp
    assert trim_messages(msgs, from_s=999.0) == []


@test
def test_replay_with_modification():
    write_candump(LOG, make_msgs())
    rx = can.Bus(interface="virtual", channel=CH)
    recv = []
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            m = rx.recv(timeout=0.1)
            if m is not None:
                recv.append(m)

    th = threading.Thread(target=loop, daemon=True)
    th.start()
    args = Namespace(interface="virtual", channel=CH, bitrate=None, tty_baud=115200,
                     silent=False, silent_mode="m1", fd=False, profile=None,
                     file=LOG, rate=10.0, max_gap=1.0, skip_ids=None, loop=False,
                     limit=12, set=["0x130:3=0x2A"], counter=["0x130:1"],
                     checksum=["0x130:7:xor8"], drop=None)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = replay_tool.run(args)
    time.sleep(0.3)
    stop.set()
    th.join(timeout=1.0)
    rx.shutdown()

    out = buf.getvalue()
    assert rc == 0, out
    assert "modyfikacje: 3" in out, out
    assert len(recv) >= 12, f"odebrano {len(recv)}"

    m = recv[3]
    assert m.data[3] == 0x2A, bytes(m.data)
    assert m.data[1] == 3, bytes(m.data)  # licznik wymuszony: 0,1,2,3...
    chk = 0
    for i, x in enumerate(m.data):
        if i != 7:
            chk ^= x
    assert m.data[7] == chk, bytes(m.data)


@test
def test_replay_drop():
    rx = can.Bus(interface="virtual", channel=CH + "2")
    recv = []
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            m = rx.recv(timeout=0.1)
            if m is not None:
                recv.append(m)

    th = threading.Thread(target=loop, daemon=True)
    th.start()
    args = Namespace(interface="virtual", channel=CH + "2", bitrate=None, tty_baud=115200,
                     silent=False, silent_mode="m1", fd=False, profile=None,
                     file=LOG, rate=20.0, max_gap=1.0, skip_ids=None, loop=False,
                     limit=10, set=[], counter=[], checksum=[], drop="0x130")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = replay_tool.run(args)
    time.sleep(0.3)
    stop.set()
    th.join(timeout=1.0)
    rx.shutdown()
    assert rc == 0, buf.getvalue()
    assert len(recv) == 0, f"drop nie zadziałał: {len(recv)} ramek"


def main() -> int:
    fails = 0
    print(f"# miriCAN Studio - testy menedżera logów ({len(TESTS)} testów)")
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
