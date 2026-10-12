"""Serwer MCP (stdio) dla miriCAN Studio — natywna integracja z agentami.

Uruchomienie::

    py -m canstudio mcp

Narzędzia wykonują polecenia ``py -m canstudio … --json`` (w podprocesie)
i zwracają wynik jako JSON-tekst; narzędzia ``gui_*`` sterują działającym
Studiem (GUI) przez ``ctl`` (REST/WebSocket).

Wymaga pakietu ``mcp`` (py -m pip install mcp).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TOOL_NAMES = [
    "can_ports", "can_sniff", "can_scan", "can_log_stats", "can_discover",
    "can_checksum", "can_correlate", "can_autodbc", "can_uds", "can_send",
    "can_replay", "gui_status", "gui_connect", "gui_frames", "gui_call",
]
TOOL_COUNT = len(TOOL_NAMES)

DEFAULT_GUI = "http://127.0.0.1:8077"
_ROOT = str(Path(__file__).resolve().parents[1])


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def _py() -> list[str]:
    return [sys.executable, "-m", "canstudio"]


def _capture(cmd: list[str], timeout: float) -> tuple[str, str, int]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, cwd=_ROOT)
    except subprocess.TimeoutExpired:
        return "", f"timeout {timeout:.0f}s", -1
    return proc.stdout or "", proc.stderr or "", proc.returncode


def _last_json(text: str):
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except Exception:  # noqa: BLE001
        return None


def _run_json(argv: list[str], timeout: float = 240.0) -> str:
    """CLI z --json: stdout = JSON; stderr = logi. Zwraca tekst JSON."""
    out, err, code = _capture(_py() + argv + ["--json"], timeout)
    obj = _last_json(out)
    if obj is None:
        tail = (err or "").strip().splitlines()
        return _dumps({"ok": False,
                       "error": tail[-1] if tail else f"exit {code}"})
    return _dumps(obj)


def _run_ctl(url: str, argv: list[str], timeout: float = 240.0) -> str:
    """ctl (zawsze JSON): zwraca sformatowany JSON."""
    out, err, code = _capture(_py() + ["ctl", "--url", url, *argv], timeout)
    obj = _last_json(out)
    if obj is None:
        tail = (err or "").strip().splitlines()
        return _dumps({"ok": False,
                       "error": tail[-1] if tail else f"exit {code}"})
    return _dumps(obj)


def build():
    """Buduje serwer MCP z zestawem narzędzi."""
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(
        name="miriCAN Studio",
        instructions=("Analiza i sterowanie magistralą CAN (canstudio/miriCAN Studio). "
                      "Narzędzia can_* działają lokalnie (logi, skany, UDS, auto-DBC); "
                      "gui_* sterują uruchomionym Studiem (GUI) po REST/WS. "
                      "TX (send/replay/uds write) tylko na postoju lub ławce testowej."),
    )

    @server.tool()
    def can_ports() -> str:
        """Lista portów COM (adaptery slcan/Canable) na tym komputerze."""
        return _run_json(["ports"], timeout=60)

    @server.tool()
    def can_sniff(channel: str, duration_s: float = 5.0, bitrate: int = 500000,
                  ids: str = "", dbc: str = "", silent: bool = False) -> str:
        """Nasłuch CAN przez duration_s s (log zapisywany w logs/).
        channel: np. 'COM7'; ids: filtr np. '0x130,0x1A0'; dbc: baza DBC do dekodowania;
        silent: nasłuch bierny (bez ACK)."""
        args = ["sniff", "--channel", channel, "--bitrate", str(bitrate),
                "--duration", str(max(0.5, float(duration_s)))]
        if ids:
            args += ["--ids", ids]
        if dbc:
            args += ["--dbc", dbc]
        if silent:
            args += ["--silent"]
        return _run_json(args, timeout=duration_s + 90)

    @server.tool()
    def can_scan(channel: str, rates: str = "125000,250000,500000,1000000",
                 per_rate_s: float = 1.0) -> str:
        """Skaner prędkości magistrali (biernie) — która bitrate daje ramki."""
        n = len([r for r in rates.split(",") if r.strip()])
        return _run_json(["scan", "--channel", channel, "--rates", rates,
                          "--per-rate", str(per_rate_s)],
                         timeout=n * per_rate_s + 90)

    @server.tool()
    def can_log_stats(file: str) -> str:
        """Statystyki logu (candump/.asc/.blf): ramki, ID, okresy, ostatnie dane."""
        return _run_json(["stats", file], timeout=120)

    @server.tool()
    def can_discover(file: str) -> str:
        """Klasyfikacja bajtów z logu per ID: stały/licznik/suma/przełącznik/sensor."""
        return _run_json(["discover", file], timeout=120)

    @server.tool()
    def can_checksum(file: str) -> str:
        """Detekcja liczników i sum kontrolnych w logu (algorytm + pewność)."""
        return _run_json(["checksum", file], timeout=120)

    @server.tool()
    def can_correlate(file: str, window_s: float = 1.5) -> str:
        """Korelacja znaczników (sniff --marks) z bajtami — co reaguje na akcję."""
        return _run_json(["correlate", file, "--window", str(window_s)], timeout=120)

    @server.tool()
    def can_autodbc(file: str) -> str:
        """Generuje wstępny plik DBC z logu (dbc/auto_<nazwa>.dbc)."""
        return _run_json(["autodbc", file], timeout=120)

    @server.tool()
    def can_uds(channel: str, action: str = "scan", txid: str = "",
                dids: str = "", ids: str = "600-6FF", clear: bool = False) -> str:
        """Diagnostyka UDS: action = 'scan' | 'read' | 'dtc'.
        read: podaj txid i dids (np. 'F190,F18C'); dtc: txid (+ clear=true kasuje DTC).
        UWAGA: TX — tylko postój/ławka."""
        if action == "scan":
            return _run_json(["uds", "scan", "--channel", channel, "--ids", ids], timeout=300)
        if action == "read":
            parts = [p.strip() for p in dids.split(",") if p.strip()]
            return _run_json(["uds", "read", "--channel", channel, "--txid", txid, *parts],
                             timeout=120)
        if action == "dtc":
            args = ["uds", "dtc", "--channel", channel, "--txid", txid]
            if clear:
                args += ["--clear", "--yes"]
            return _run_json(args, timeout=120)
        return _dumps({"ok": False, "error": f"nieznana akcja {action!r}"})

    @server.tool()
    def can_send(channel: str, frame_id: str, data: str, count: int = 1,
                 interval_s: float = 0.1, extended: bool = False) -> str:
        """Wyślij ramkę CAN. frame_id np. '0x123'; data hex np. 'DE AD BE EF'.
        UWAGA: TX — tylko postój/ławka."""
        args = ["send", "--channel", channel, "--id", str(frame_id), "--data", data,
                "--count", str(int(count)), "--interval", str(interval_s)]
        if extended:
            args += ["--extended"]
        return _run_json(args, timeout=120)

    @server.tool()
    def can_replay(file: str, channel: str, rate: float = 1.0, set_: str = "",
                   counter: str = "", checksum: str = "", drop: str = "") -> str:
        """Odtwórz log na magistralę, opcjonalnie z modyfikacjami:
        set_ np. '0x130:3=0x2A'; counter '0x130:1'; checksum '0x130:7:xor8';
        drop '0x2C0'. UWAGA: TX — tylko postój/ławka."""
        args = ["replay", file, "--channel", channel, "--rate", str(rate)]
        if set_:
            args += ["--set", set_]
        if counter:
            args += ["--counter", counter]
        if checksum:
            args += ["--checksum", checksum]
        if drop:
            args += ["--drop", drop]
        return _run_json(args, timeout=600)

    # --- GUI (działające Studio) ---

    @server.tool()
    def gui_status(url: str = DEFAULT_GUI) -> str:
        """Status działającego Studia (połączenie, DBC, TX, replay, trigger, profil)."""
        return _run_ctl(url, ["status"], timeout=30)

    @server.tool()
    def gui_connect(url: str = DEFAULT_GUI, interface: str = "virtual",
                    port: str = "gui-demo", bitrate: int = 500000,
                    demo: bool = False, silent: bool = False) -> str:
        """Połącz magistralę w Studiu. interface='virtual' → kanał demo."""
        args = ["connect", "--interface", interface, "--bitrate", str(bitrate)]
        if interface != "virtual" and port:
            args += ["--port", port]
        if demo:
            args += ["--demo"]
        if silent:
            args += ["--silent"]
        return _run_ctl(url, args, timeout=60)

    @server.tool()
    def gui_frames(url: str = DEFAULT_GUI, seconds: float = 5.0,
                   max_frames: int = 500) -> str:
        """Pobierz żywe ramki z sesji GUI: {"ok":true,"count":N,"frames":[{t,id,x,d,n}]}."""
        cmd = _py() + ["ctl", "--url", url, "frames",
                       "--seconds", str(seconds), "--max", str(int(max_frames))]
        out, err, code = _capture(cmd, timeout=seconds + 60)
        frames = []
        for line in out.strip().splitlines():
            obj = _last_json(line)
            if obj is not None:
                frames.append(obj)
        if not frames and code != 0:
            tail = (err or "").strip().splitlines()
            return _dumps({"ok": False, "error": tail[-1] if tail else f"exit {code}"})
        return _dumps({"ok": True, "count": len(frames), "frames": frames})

    @server.tool()
    def gui_call(url: str = DEFAULT_GUI, path: str = "/api/status",
                 method: str = "GET", body: str = "") -> str:
        """Dowolne wywołanie REST Studia — pełny dostęp do GUI.
        Przykłady: path='/api/log/stats', body='{"file":"demo_b.log"}';
        path='/api/uds/scan', body='{"ids":"600-6FF"}'; path='/api/dbc/list'."""
        args = ["call", path, "--method", method.upper()]
        if body:
            args += ["--body", body]
        return _run_ctl(url, args, timeout=600)

    return server


def run(args) -> int:
    try:
        server = build()
    except ModuleNotFoundError as exc:
        print("# Brak pakietu 'mcp'. Zainstaluj: py -m pip install mcp")
        print(f"# ({exc})")
        return 1
    server.run(transport="stdio")
    return 0
