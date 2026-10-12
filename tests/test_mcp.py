# -*- coding: utf-8 -*-
"""Testy serwera MCP (stdio): handshake, tools/list, tools/call.

Uruchomienie:
    py tests/test_mcp.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import queue
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


@test
def test_tool_registry():
    from canstudio import mcp_server

    assert mcp_server.TOOL_COUNT == len(mcp_server.TOOL_NAMES)
    assert mcp_server.TOOL_COUNT >= 12
    assert "can_ports" in mcp_server.TOOL_NAMES
    assert "gui_call" in mcp_server.TOOL_NAMES


@test
def test_stdio_protocol():
    if importlib.util.find_spec("mcp") is None:
        raise AssertionError("brak pakietu mcp (py -m pip install mcp)")
    proc = subprocess.Popen(
        [sys.executable, "-m", "canstudio", "mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, cwd=ROOT)
    q: queue.Queue = queue.Queue()

    def reader():
        for line in proc.stdout:
            q.put(line)

    threading.Thread(target=reader, daemon=True).start()

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "miritest", "version": "0.1"}}})
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
          "params": {"name": "can_ports", "arguments": {}}})

    got = {}
    deadline = time.time() + 60
    try:
        while time.time() < deadline and len(got) < 3:
            try:
                line = q.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                msg = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(msg, dict) and msg.get("id") in (1, 2, 3) and "result" in msg:
                got[msg["id"]] = msg
    finally:
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass

    assert 1 in got, "brak odpowiedzi initialize"
    assert "miriCAN" in json.dumps(got[1]["result"], ensure_ascii=False), got[1]
    names = [t["name"] for t in got[2]["result"]["tools"]]
    assert "can_ports" in names and len(names) >= 12, names
    text = got[3]["result"]["content"][0]["text"]
    assert '"ports"' in text, text[:200]


def main() -> int:
    fails = 0
    print(f"# miriCAN Studio - testy serwera MCP ({len(TESTS)} testów)")
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
