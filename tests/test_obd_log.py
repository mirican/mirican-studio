# -*- coding: utf-8 -*-
"""Testy sesji OBD (obd-logger/1): zapis, odczyt, statystyki, serie, pobieranie.

Uruchomienie:
    py tests/test_obd_log.py
"""

from __future__ import annotations

import http.server
import json
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from canstudio.obd_log import (SessionWriter, fetch_file,  # noqa: E402
                               fetch_manifest, parse_session, series,
                               session_stats)

TESTS = []
TMP = tempfile.mkdtemp(prefix="obd_log_test_")


def test(fn):
    TESTS.append(fn)
    return fn


@test
def test_writer_roundtrip():
    w = SessionWriter(TMP, vehicle="test", adapter="faux", pids=["010C", "0105"])
    w.pid("010C", "EngineRPM", 800.0, "rpm", t_ms=1000)
    w.pid("010C", "EngineRPM", 900.0, "rpm", t_ms=1500)
    w.pid("0105", "CoolantTemp", 25.0, "C", t_ms=1600)
    w.event("mark", {"x": 1})
    w.close()
    meta, recs = parse_session(w.path)
    assert meta["format"] == "obd-logger/1", meta
    assert meta["vehicle"] == "test" and meta["pids"] == ["010C", "0105"], meta
    assert len(recs) == 4, recs


@test
def test_stats_and_series():
    w = SessionWriter(TMP)
    for i in range(10):
        w.pid("010C", "EngineRPM", 800 + i * 10, "rpm", t_ms=1000 + i * 100)
    w.pid("0105", "CoolantTemp", 20.0, "C", t_ms=1000)
    w.close()
    _meta, recs = parse_session(w.path)
    st = session_stats(recs)
    row = [p for p in st["pids"] if p["pid"] == "010C"][0]
    assert row["count"] == 10 and row["min"] == 800 and row["max"] == 890, row
    assert abs(row["avg"] - 845.0) < 0.01, row
    assert st["duration_s"] == 0.9, st
    ser = series(recs, "010C", max_points=5)
    assert ser["records"] == 10 and ser["count"] == 5, ser


@test
def test_parse_bad_lines():
    p = os.path.join(TMP, "obd_20260101_000000.jsonl")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write('{"kind":"meta","format":"obd-logger/1"}\n')
        fh.write("to nie json\n")
        fh.write('{"kind":"pid","t":1,"pid":"010C","value":1.0}\n')
    meta, recs = parse_session(p)
    assert meta is not None and len(recs) == 1, recs


@test
def test_device_fetch_mock():
    # lokalny HTTP jako atrapa loggera ESP32 (kontrakt: manifest.json + /files/<n>)
    d = os.path.join(TMP, "device")
    os.makedirs(os.path.join(d, "files"), exist_ok=True)
    with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({"files": [{"name": "obd_1.jsonl", "size": 14, "mtime": 0}]}, fh)
    with open(os.path.join(d, "files", "obd_1.jsonl"), "w", encoding="utf-8") as fh:
        fh.write('{"kind":"meta"}\n')

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=d, **kw)

        def log_message(self, *a):  # wycisz
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{port}"
        man = fetch_manifest(url)
        assert man["ok"] and man["files"][0]["name"] == "obd_1.jsonl", man
        dest = os.path.join(TMP, "dl")
        res = fetch_file(url, "obd_1.jsonl", dest_dir=dest)
        assert res["ok"] and res["size"] > 0, res
        assert os.path.exists(os.path.join(dest, "obd_1.jsonl"))
        bad = fetch_file(url, "..\\..\\evil", dest_dir=dest)
        assert not bad["ok"], bad
        bad2 = fetch_manifest("http://127.0.0.1:1")
        assert not bad2["ok"], bad2
    finally:
        httpd.shutdown()


def main() -> int:
    fails = 0
    print(f"# miriCAN Studio - testy sesji OBD ({len(TESTS)} testów)")
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
