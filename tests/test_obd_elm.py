# -*- coding: utf-8 -*-
"""Testy warstwy OBD/ELM327 (syntetyczne, bez sprzetu).

Uruchomienie:
    py tests/test_obd_elm.py
"""

from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from canstudio.elm327 import Elm327, clean_response, find_elm_port  # noqa: E402
from canstudio.obd import (collect_bytes, decode_dtc, norm_pid,  # noqa: E402
                           parse_dtc, parse_payload, parse_pid, parse_vin,
                           payloads_from_resp, read_pid, read_pids,
                           read_supported)

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


# --- falszywy port szeregowy (skrypt odpowiedzi) ---------------------------

SCRIPT = {
    "ATZ": "ATZ\r\r\rELM327 v2.3\r\r>",
    "ATE0": "ATE0\rOK\r\r>",
    "ATL0": "ATL0\rOK\r\r>",
    "ATS1": "ATS1\rOK\r\r>",
    "ATH1": "ATH1\rOK\r\r>",
    "ATAT1": "ATAT1\rOK\r\r>",
    "ATSP0": "ATSP0\rOK\r\r>",
    "ATSP6": "ATSP6\rOK\r\r>",
    "ATI": "ATI\rELM327 v2.3\r\r>",
    "ATRV": "ATRV\r12.2V\r\r>",
    "0100": "0100\r7E8 06 41 00 BE 3F A8 13\r\r>",
    "0120": "0120\r7E8 06 41 20 80 00 00 00\r\r>",
    "0105": "0105\rNO DATA\r\r>",
    "0166": "0166\r7E8 04 41 66 12 34\r\r>",
    "010C": "010C\r7E8 04 41 0C 1A F8\r\r>",
    "010C05": "010C05\r7E8 06 41 0C 1A F8 05 7B\r\r>",
    "03": "03\r7E8 07 43 01 23 81 45 00 00\r\r>",
    "0902": ("0902\r7E8 10 14 49 02 01 57 42 41\r"
             "7E8 21 33 41 35 43 35 30\r"
             "7E8 22 45 46 31 32 33 34 35 36\r\r>"),
}


class FakeSerial:
    """Miniatrowy port: na komende odpowiada zadanym tekstem."""

    def __init__(self, script):
        self.script = {k.upper(): v for k, v in script.items()}
        self.out = b""
        self.commands = []
        self.closed = False

    def write(self, data):
        cmd = bytes(data).decode("ascii", "replace").strip()
        self.commands.append(cmd)
        resp = self.script.get(cmd.upper(), "")
        if isinstance(resp, list):  # lista odpowiedzi (kolejne wywolania)
            resp = resp.pop(0) if resp else ""
        if resp:
            self.out += resp.encode("ascii", "replace")
        return len(data)

    def flush(self):
        pass

    def reset_input_buffer(self):
        pass

    def read(self, n=256):
        chunk = self.out[:n]
        self.out = self.out[n:]
        return chunk

    def close(self):
        self.closed = True


def make_elm(script=None):
    elm = Elm327("FAKE", opener=lambda: FakeSerial(script or SCRIPT))
    elm.open()
    return elm


# --- testy ------------------------------------------------------------------

@test
def test_clean_response():
    assert clean_response("ATZ\r\r\rELM327 v2.3\r\r>", "ATZ") == "ELM327 v2.3"
    assert clean_response("OK\r\r>", "ATE0") == "OK"
    assert ">" not in clean_response("12.2V\r\r>", "ATRV")


@test
def test_norm_pid():
    assert norm_pid("010C") == 0x0C
    assert norm_pid("0C") == 0x0C
    assert norm_pid("0x0c") == 0x0C
    assert norm_pid("5E") == 0x5E
    # PowerShell czasem zamienia '0105' na liczbe 105 (zjada wiodace zero)
    assert norm_pid("105") == 0x05
    assert norm_pid("120") == 0x20


@test
def test_collect_bytes_skips_ids():
    b = collect_bytes("7E8 04 41 0C 1A F8")
    assert b == [0x04, 0x41, 0x0C, 0x1A, 0xF8], b
    b = collect_bytes("18DAF110 06 41 00 BE 3F A8 13")
    assert b == [0x06, 0x41, 0x00, 0xBE, 0x3F, 0xA8, 0x13], b


@test
def test_cmd_and_init():
    elm = make_elm()
    r = elm.cmd("ATZ")
    assert "ELM327" in r, r
    r = elm.cmd("ATE0")
    assert r == "OK", r
    info = elm.init()
    assert "ELM327" in info["adapter"], info
    assert "12.2" in info["voltage"], info


@test
def test_parse_pid_rpm():
    val, raw = parse_pid("7E8 04 41 0C 1A F8", 0x0C)
    assert raw == b"\x1a\xf8", raw
    assert abs(val - 1726.0) < 0.01, val


@test
def test_parse_pid_coolant():
    val, raw = parse_pid("41 05 7B", 0x05)
    assert raw == b"\x7b"
    assert abs(val - 83.0) < 0.01, val  # 0x7B = 123 -> 123 - 40


@test
def test_read_pids_via_fake():
    elm = make_elm()
    rows = read_pids(elm, [0x0C, 0x05])
    assert rows[0]["status"] == "ok" and abs(rows[0]["value"] - 1726.0) < 0.01, rows
    assert rows[1]["status"] == "ok" and abs(rows[1]["value"] - 83.0) < 0.01, rows  # batch 010C05


@test
def test_read_pids_batch_fallback():
    script = dict(SCRIPT)
    script["010C05"] = "010C05\rNO DATA\r\r>"  # batch zawodzi -> fallback pojedynczy
    elm = make_elm(script)
    rows = read_pids(elm, [0x0C, 0x05])
    assert rows[0]["status"] == "ok" and abs(rows[0]["value"] - 1726.0) < 0.01, rows
    assert rows[1]["status"] == "nodata", rows


@test
def test_read_pids_unknown_decoder():
    elm = make_elm()
    rows = read_pids(elm, [0x66])
    r = rows[0]
    assert r["status"] == "ok" and r["value"] is None and r["data"], r
    assert r["name"] == "PID_UNKNOWN", r


@test
def test_multi_payload_parse():
    resp = "7E8 06 41 0C 00 00 0D 00\n7E9 06 41 0C 00 00 0D 00"
    pls = payloads_from_resp(resp)
    assert len(pls) == 2 and pls[0] == bytes([0x41, 0x0C, 0x00, 0x00, 0x0D, 0x00]), pls
    got = parse_payload(pls[0])
    assert got[0x0C][0] == 0.0 and got[0x0D][0] == 0.0, got
    # wielo-ramkowa odpowiedz (4 PID-y > 7 bajtow): FF + CF
    resp2 = ("7E8 10 0A 41 0C 00 00 0D 00\n"
             "7E8 21 05 40 2F 23 AA AA AA")
    pls2 = payloads_from_resp(resp2)
    assert len(pls2) == 1, pls2
    got2 = parse_payload(pls2[0])
    assert got2[0x0C][0] == 0.0 and got2[0x0D][0] == 0.0, got2
    assert abs(got2[0x05][0] - 24.0) < 0.01 and abs(got2[0x2F][0] - 13.725) < 0.01, got2
    # linie dwoch ECU przeplatane (realny przypadek z auta)
    resp3 = ("7E9 10 08 41 0C 00 00 0D 00\n"
             "7E8 10 0A 41 0C 00 00 0D 00\n"
             "7E9 21 05 40 AA AA AA AA AA\n"
             "7E8 21 05 40 2F 23 AA AA AA")
    pls3 = payloads_from_resp(resp3)
    assert len(pls3) == 2, pls3
    merged = {}
    for pl in pls3:
        for k, v in parse_payload(pl).items():
            merged.setdefault(k, v)
    assert merged[0x0C][0] == 0.0 and merged[0x0D][0] == 0.0, merged
    assert abs(merged[0x05][0] - 24.0) < 0.01 and abs(merged[0x2F][0] - 13.725) < 0.01, merged


@test
def test_decode_and_parse_dtc():
    assert decode_dtc(0x01, 0x23) == "P0123"
    assert decode_dtc(0x81, 0x45) == "B0145"
    codes = parse_dtc("7E8 07 43 01 23 81 45 00 00")
    assert codes == ["P0123", "B0145"], codes
    assert parse_dtc("NO DATA") == []
    # dwa ECU na magistrali, oba "43 00" (brak kodow) - nie wolno zlepac w pary
    assert parse_dtc("7E8 02 43 00\n7E9 02 43 00") == []
    assert parse_dtc("43 01 23 00 00") == ["P0123"]


@test
def test_read_pid_searching_retry():
    script = dict(SCRIPT)
    script["010C"] = ["010C\rSEARCHING...\r\r>", "010C\r7E8 04 41 0C 1A F8\r\r>"]
    elm = make_elm(script)
    r = read_pid(elm, 0x0C, timeout=1.0)
    assert r["status"] == "ok" and abs(r["value"] - 1726.0) < 0.01, r


@test
def test_parse_vin():
    resp = ("7E8 10 14 49 02 01 57 42 41\r"
            "7E8 21 33 41 35 43 35 30\r"
            "7E8 22 45 46 31 32 33 34 35 36")
    assert parse_vin(resp) == "WBA3A5C50EF123456", parse_vin(resp)


@test
def test_read_supported_bitmap():
    elm = make_elm()
    sup = read_supported(elm)
    assert 0x0C in sup and 0x0D in sup and 0x01 in sup, sup
    assert 0x20 in sup and 0x21 in sup, sup   # 0x20 z bitmapy 0100, 0x21 z 0120
    assert 0x40 not in sup, sup               # LSB=0 -> lancuch konczy sie na 0120


@test
def test_find_port_no_crash():
    # na maszynie bez vLinkera zwroci (None, None); nie moze rzucic wyjatku
    port, why = find_elm_port()
    assert port is None or isinstance(port, str)


@test
def test_obd_session_monitor_save():
    import tempfile
    from canstudio.obd import ObdSession

    events = []
    sess = ObdSession(opener=lambda: FakeSerial(dict(SCRIPT)), push=events.append)
    r = sess.open(port="FAKE", warm_timeout=3.0)
    assert r["ok"] and r["bus"] is True, r
    tmp = tempfile.mkdtemp(prefix="obd_sess_")
    r2 = sess.monitor_start(["010C", "0105"], interval=0.05, save=True, save_dir=tmp)
    assert r2["ok"] and r2["saved"], r2
    time.sleep(0.5)
    r3 = sess.monitor_stop()
    assert r3["ok"] and r3["rounds"] >= 2, r3
    assert any(e.get("e") == "pid" and e.get("status") == "ok" for e in events), events[:6]
    sess.close()
    files = [f for f in os.listdir(tmp) if f.endswith(".jsonl")]
    assert files, r2
    with open(os.path.join(tmp, files[0]), encoding="utf-8") as fh:
        content = fh.read()
    assert '"kind": "meta"' in content and '"pid": "010C"' in content, content[:300]


def main() -> int:
    fails = 0
    print(f"# miriCAN Studio - testy OBD/ELM327 ({len(TESTS)} testow)")
    for fn in TESTS:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            fails += 1
            print(f"  FAIL  {fn.__name__}: {type(exc).__name__}: {exc}")
    total = len(TESTS)
    print(f"# wynik: {total - fails}/{total} OK")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
