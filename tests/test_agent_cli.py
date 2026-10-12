# -*- coding: utf-8 -*-
"""Testy trybu agentowego: --json/--jsonl oraz klient `ctl`.

Uruchomienie:
    py tests/test_agent_cli.py
"""

from __future__ import annotations

import io
import json
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

from canstudio import json_cli  # noqa: E402
from canstudio.tools import ctl as ctl_tool  # noqa: E402
from canstudio.tools import discover as discover_tool  # noqa: E402
from canstudio.tools import sniff as sniff_tool  # noqa: E402

TESTS = []
LOG = os.path.join(ROOT, "logs", "_test_agent.log")
CH = "agent-cli-test"


def test(fn):
    TESTS.append(fn)
    return fn


def make_log():
    msgs = []
    for i in range(60):
        body = [0x03, i & 0xFF, 0x10, (i * 7) & 0xFF, 0x80, 0, 0, 0]
        chk = 0
        for x in body[:7]:
            chk ^= x
        body[7] = chk
        m = can.Message(arbitration_id=0x130, is_extended_id=False, data=bytes(body))
        m.timestamp = 1000 + i * 0.02
        msgs.append(m)
    from canstudio.logio import write_candump

    write_candump(LOG, msgs)


@test
def test_emit_and_json_mode():
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        assert json_cli.json_mode(Namespace(json=True)) is True
        print("human-text")  # powinno trafić na stderr
        json_cli.emit({"ok": True, "x": 1})
    finally:
        json_cli.reset()
        sys.stdout = old
    out = buf.getvalue()
    assert json.loads(out.strip())["x"] == 1, out
    assert "human-text" not in out


@test
def test_discover_json():
    make_log()
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc = discover_tool.run(Namespace(log=LOG, ids=None, top=5, min_frames=12,
                                         json=True, jsonl=False))
    finally:
        json_cli.reset()
        sys.stdout = old
    assert rc == 0
    data = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert data["ok"] and data["ids"], data
    kinds = [c["kind"] for c in data["ids"][0]["classes"]]
    assert "licznik" in kinds and "suma" in kinds, kinds


@test
def test_sniff_jsonl_virtual():
    def feeder():
        bus = can.Bus(interface="virtual", channel=CH)
        t0 = time.time()
        try:
            for i in range(12):
                m = can.Message(arbitration_id=0x123, is_extended_id=False,
                                data=bytes([i, 1, 2, 3]))
                m.timestamp = t0 + i * 0.05
                bus.send(m)
                time.sleep(0.05)
        finally:
            bus.shutdown()

    th = threading.Thread(target=feeder, daemon=True)
    th.start()
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc = sniff_tool.run(Namespace(
            interface="virtual", channel=CH, bitrate=500000, tty_baud=115200,
            silent=False, silent_mode="m1", fd=False, profile=None, dbc=None,
            ids=None, hide_ids=None, duration=1.2, count=0, log_dir=None,
            no_log=True, quiet=False, marks=False, list_ports=False,
            json=False, jsonl=True))
    finally:
        json_cli.reset()
        sys.stdout = old
    th.join(timeout=2)
    assert rc == 0
    lines = [l for l in buf.getvalue().splitlines() if l.strip()]
    frames = [json.loads(l) for l in lines]
    assert len(frames) >= 5, lines
    assert frames[0]["id"] == 0x123 and frames[0]["x"] == 0 and "d" in frames[0], frames[0]


@test
def test_ctl_client_mini_server():
    import http.server

    class Handler(http.server.BaseHTTPRequestHandler):
        def _reply(self):
            body = json.dumps({"ok": True, "path": self.path, "total": 42}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = _reply
        do_POST = _reply

        def log_message(self, *a):  # cisza w testach
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    base = f"http://127.0.0.1:{port}"
    try:
        out = io.StringIO()
        with redirect_stdout(out):
            rc = ctl_tool.run(Namespace(url=base, pretty=False, timeout=5.0,
                                        cmd="status", _fn=ctl_tool.cmd_status))
        assert rc == 0
        assert json.loads(out.getvalue().strip())["total"] == 42

        out2 = io.StringIO()
        with redirect_stdout(out2):
            rc2 = ctl_tool.run(Namespace(url=base, pretty=False, timeout=5.0,
                                         cmd="call", _fn=ctl_tool.cmd_call,
                                         path="/api/x", method="POST", body='{"a":1}'))
        assert rc2 == 0
        assert json.loads(out2.getvalue().strip())["path"] == "/api/x"

        # serwer nie odpowiada -> kod 2 i JSON z błędem
        out3 = io.StringIO()
        with redirect_stdout(out3):
            rc3 = ctl_tool.run(Namespace(url="http://127.0.0.1:1", pretty=False,
                                         timeout=0.5, cmd="status",
                                         _fn=ctl_tool.cmd_status))
        assert rc3 == 2, rc3
        assert json.loads(out3.getvalue().strip())["ok"] is False
    finally:
        srv.shutdown()


def main() -> int:
    fails = 0
    print(f"# miriCAN Studio - testy agentowe ({len(TESTS)} testów)")
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
