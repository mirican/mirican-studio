# -*- coding: utf-8 -*-
"""Testy syntetyczne UDS/ISO-TP na magistrali wirtualnej (bez sprzętu).

Uruchomienie:
    py tests/test_uds_virtual.py

Testy pokrywają:
* warstwę ``canstudio.diag`` (parsowanie, skaner, klient UDS),
* narzędzie ``canstudio.tools.uds`` (scan/read/write/dtc/session/reset/raw),
* pełny łańcuch ISO-TP ↔ UDS z mockiem ECU na magistrali wirtualnej.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import threading
import time
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import can  # noqa: E402

from canstudio import diag  # noqa: E402
from canstudio.tools import uds as uds_tool  # noqa: E402

CH = "canstudio_uds_test"
TXID, RXID = 0x6F1, 0x6F9
MOCK = None

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


# ---------------------------------------------------------------------------
# Mock ECU (odpowiada jak sterownik po ISO-TP na magistrali wirtualnej)
# ---------------------------------------------------------------------------

class MockECU(threading.Thread):
    def __init__(self, channel, txid=RXID, rxid=TXID):
        super().__init__(daemon=True)
        self.channel = channel
        self.txid = txid
        self.rxid = rxid
        self.stop_evt = threading.Event()
        self.written = {}
        self.cleared = 0
        self.vin = b"WBA5E510X0G123456"
        self.serial = b"SN12345678"

    def handle(self, req: bytes):
        sid = req[0]
        if sid == 0x3E:  # TesterPresent
            if len(req) > 1 and req[1] & 0x80:
                return None
            return bytes([0x7E, req[1] if len(req) > 1 else 0])
        if sid == 0x10:  # session control
            return bytes([0x50, req[1], 0x00, 0x32, 0x01, 0xF4])
        if sid == 0x22:  # read DID
            did = int.from_bytes(req[1:3], "big")
            if did == 0xF190:
                return bytes([0x62, 0xF1, 0x90]) + self.vin
            if did == 0xF18C:
                return bytes([0x62, 0xF1, 0x8C]) + self.serial
            if did == 0xF187:
                return b"\x62\xF1\x87BMW 6885582"
            if did == 0xF1A0 and 0xF1A0 in self.written:
                return bytes([0x62, 0xF1, 0xA0]) + self.written[0xF1A0]
            return bytes([0x7F, 0x22, 0x31])  # requestOutOfRange
        if sid == 0x2E:  # write DID
            did = int.from_bytes(req[1:3], "big")
            self.written[did] = bytes(req[3:])
            return bytes([0x6E]) + req[1:3]
        if sid == 0x19:  # read DTC
            return (b"\x59\x02\xFF"
                    + bytes([0x12, 0x34, 0x56, 0x24])
                    + bytes([0xAB, 0xC0, 0x01, 0x2F]))
        if sid == 0x14:  # clear DTC
            self.cleared += 1
            return b"\x54"
        if sid == 0x11:  # ECU reset
            return bytes([0x51, req[1] if len(req) > 1 else 0x01])
        return bytes([0x7F, sid, 0x11])  # serviceNotSupported

    def run(self):
        bus = can.Bus(interface="virtual", channel=self.channel)
        tp = diag.open_isotp(bus, self.txid, self.rxid)
        tp.start()
        try:
            while not self.stop_evt.is_set():
                req = tp.recv(block=True, timeout=0.1)
                if not req:
                    continue
                resp = self.handle(bytes(req))
                if resp:
                    tp.send(resp)
        finally:
            diag.close_session(bus=bus, tp=tp)

    def stop(self):
        self.stop_evt.set()
        self.join(timeout=2)


# ---------------------------------------------------------------------------
# Pomocnicze
# ---------------------------------------------------------------------------

def ns(**over):
    args = argparse.Namespace(
        interface="virtual", channel=CH, bitrate=500000, tty_baud=115200,
        silent=False, silent_mode="m1", fd=False, ext=False, profile=None,
        txid=None, rxid=None, session=None,
        ids="600-6FF", offset=8, probe="3E00", timeout=1.0,
        dids=None, did=None, data=None, yes=False, clear=False, mask="FF",
        type="1", payload=None,
    )
    for key, value in over.items():
        setattr(args, key, value)
    return args


def run_capture(fn, args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = fn(args)
    return rc, buf.getvalue()


def expect_exit(fn, args, needle):
    try:
        with redirect_stdout(io.StringIO()):
            fn(args)
    except SystemExit as exc:
        assert needle.lower() in str(exc).lower(), f"inny komunikat: {exc}"
        return
    raise AssertionError("oczekiwano SystemExit")


# ---------------------------------------------------------------------------
# Testy
# ---------------------------------------------------------------------------

@test
def test_parse_helpers():
    assert diag.parse_hex("6F1") == 0x6F1
    assert diag.parse_hex("0xF190") == 0xF190
    assert diag.parse_hex_bytes("01 02 FF") == b"\x01\x02\xff"
    assert diag.parse_hex_bytes("0x01,0x02") == b"\x01\x02"
    assert diag.parse_ids_spec("6F0-6F2") == [0x6F0, 0x6F1, 0x6F2]
    assert diag.parse_ids_spec("6F1, 700") == [0x6F1, 0x700]
    assert diag.make_single_frame(b"\x3E\x00") == bytes([2, 0x3E, 0, 0, 0, 0, 0, 0])
    assert diag.code_name(0x31) == "RequestOutOfRange"
    assert diag.did_name(0xF190) == "vin"
    assert "WBA" in diag.fmt_bytes(b"WBA\x00") or "57 42 41" in diag.fmt_bytes(b"WBA\x00")


@test
def test_scan_finds_mock():
    rc, out = run_capture(uds_tool.cmd_scan, ns(
        ids="6F0-6F2", offset=8, probe="3E00", timeout=0.15))
    assert rc == 0
    assert "1 odpowiedzi" in out, out
    assert "0x6F1 -> 0x6F9" in out, out
    assert "7E 00" in out, out


@test
def test_scan_probe_1001():
    rc, out = run_capture(uds_tool.cmd_scan, ns(
        ids="6F1,6F3", offset=8, probe="1001", timeout=0.15))
    assert "50 01 00 32 01 F4" in out, out


@test
def test_read_vin_multiframe():
    rc, out = run_capture(uds_tool.cmd_read, ns(txid="6F1", dids=["F190"]))
    assert rc == 0
    assert "[0xF190]" in out and "(vin)" in out, out
    assert "WBA5E510X0G123456" in out, out
    assert "57 42 41" in out, out  # hex "WBA..."
    assert "F1 90 57" not in out  # bez echo DID


@test
def test_read_negative():
    rc, out = run_capture(uds_tool.cmd_read, ns(txid="6F1", dids=["1234"]))
    assert "NEGATYWNIE" in out and "RequestOutOfRange" in out, out


@test
def test_info_bundle():
    rc, out = run_capture(uds_tool.cmd_info, ns(txid="6F1"))
    assert rc == 0
    assert "[0xF190]" in out and "SN12345678" in out, out


@test
def test_write_and_readback():
    rc, out = run_capture(uds_tool.cmd_write, ns(
        txid="6F1", did="F1A0", data="01 02 03", yes=True))
    assert rc == 0 and "zapis OK" in out, out
    assert MOCK.written.get(0xF1A0) == b"\x01\x02\x03"
    rc, out = run_capture(uds_tool.cmd_read, ns(txid="6F1", dids=["F1A0"]))
    assert "01 02 03" in out, out
    assert "F1 A0 01" not in out  # bez echo DID


@test
def test_write_requires_yes():
    expect_exit(uds_tool.cmd_write, ns(txid="6F1", did="F1A0", data="00"), "--yes")


@test
def test_dtc_read_and_clear():
    rc, out = run_capture(uds_tool.cmd_dtc, ns(txid="6F1", mask="FF"))
    assert rc == 0
    assert "0x123456" in out and "status=0x24" in out, out
    assert "0xABC001" in out, out

    expect_exit(uds_tool.cmd_dtc, ns(txid="6F1", mask="FF", clear=True), "--yes")

    cleared_before = MOCK.cleared
    rc, out = run_capture(uds_tool.cmd_dtc, ns(txid="6F1", mask="FF", clear=True, yes=True))
    assert "kasowanie DTC: OK" in out, out
    assert MOCK.cleared == cleared_before + 1


@test
def test_session():
    rc, out = run_capture(uds_tool.cmd_session, ns(txid="6F1", type="3"))
    assert "sesja 0x03: OK" in out, out


@test
def test_reset():
    expect_exit(uds_tool.cmd_reset, ns(txid="6F1", type="1"), "--yes")
    rc, out = run_capture(uds_tool.cmd_reset, ns(txid="6F1", type="1", yes=True))
    assert "reset 0x01: OK" in out, out


@test
def test_raw_nrc():
    rc, out = run_capture(uds_tool.cmd_raw, ns(txid="6F1", payload="22 12 34", timeout=1.0))
    assert "7F 22 31" in out, out
    assert "NRC: RequestOutOfRange" in out, out


@test
def test_raw_dangerous_guard():
    expect_exit(uds_tool.cmd_raw, ns(txid="6F1", payload="11 01", timeout=1.0), "--yes")
    rc, out = run_capture(uds_tool.cmd_raw, ns(txid="6F1", payload="11 01",
                                              timeout=1.0, yes=True))
    assert "51 01" in out, out


@test
def test_session_via_read():
    rc, out = run_capture(uds_tool.cmd_read, ns(txid="6F1", dids=["F18C"], session="3"))
    assert "sesja 0x03: OK" in out and "SN12345678" in out, out


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> int:
    global MOCK
    MOCK = MockECU(CH)
    MOCK.start()
    time.sleep(0.3)
    fails = 0
    print(f"# miriCAN Studio - testy UDS na magistrali wirtualnej ({len(TESTS)} testów)")
    try:
        for fn in TESTS:
            try:
                fn()
                print(f"  PASS  {fn.__name__}")
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print(f"  FAIL  {fn.__name__}: {type(exc).__name__}: {exc}")
    finally:
        MOCK.stop()
    total = len(TESTS)
    print(f"# wynik: {total - fails}/{total} OK")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
