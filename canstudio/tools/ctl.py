"""Narzędzie: ctl — klient sterujący działającym miriCAN Studio (dla agentów).

Wysyła komendy do lokalnego serwera GUI (``py -m canstudio gui``) po REST
i strumieniuje ramki po WebSocket. Domyślnie drukuje **JSON** (kompaktowo);
``--pretty`` dla czytelności. Kod wyjścia: 0 = ok, 2 = błąd/serwer niedostępny.

Przykłady::

    py -m canstudio ctl status
    py -m canstudio ctl connect --interface virtual --demo
    py -m canstudio ctl frames --seconds 5 --summary
    py -m canstudio ctl uds-scan --ids 600-6FF
    py -m canstudio ctl uds-read --txid 6F1 --dids F190,F18C
    py -m canstudio ctl log-stats --file demo_b.log
    py -m canstudio ctl replay-start --file demo_b.log --rate 2 --rules '{"set":[{"id":"0x130","byte":3,"value":"231"}]}'
    py -m canstudio ctl call /api/status
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

from ..annotations import key_of

NAME = "ctl"
HELP = "Klient do działającego Studia: zdalne sterowanie po REST/WS (JSON — dla agentów)"

DEFAULT_URL = "http://127.0.0.1:8077"


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _req(args, method: str, path: str, body=None):
    url = args.url.rstrip("/") + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return json.loads(raw)
            except Exception:  # noqa: BLE001
                return {"ok": True, "raw": raw}
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": f"HTTP {exc.code}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False,
                "error": f"serwer nie odpowiada ({exc}) — uruchom: py -m canstudio gui"}


def _dump(obj, pretty: bool = False) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2 if pretty else None)
    try:
        print(text)
    except UnicodeEncodeError:
        print(json.dumps(obj, ensure_ascii=True, indent=2 if pretty else None))


def _out(res, args, code: int = 0) -> int:
    _dump(res, getattr(args, "pretty", False))
    return code if res.get("ok", True) else 2


def _ids_pair(args):
    """(txid, rxid) z --txid/--rxid; rxid domyślnie +8."""
    from .uds import _diag  # leniwe — unika importu udsoncan przy --help

    tx = _diag().parse_hex(args.txid)
    rx = _diag().parse_hex(args.rxid) if getattr(args, "rxid", None) else tx + 8
    return tx, rx


# ---------------------------------------------------------------------------
# Podkomendy
# ---------------------------------------------------------------------------

def cmd_status(args) -> int:
    return _out(_req(args, "GET", "/api/status"), args)


def cmd_ports(args) -> int:
    return _out(_req(args, "GET", "/api/ports"), args)


def cmd_connect(args) -> int:
    port = args.port or ("gui-demo" if args.interface == "virtual" else "")
    body = {"interface": args.interface, "port": port, "bitrate": args.bitrate,
            "silent": args.silent, "demo": args.demo}
    return _out(_req(args, "POST", "/api/connect", body), args)


def cmd_disconnect(args) -> int:
    return _out(_req(args, "POST", "/api/disconnect", {}), args)


def cmd_send(args) -> int:
    body = {"id": args.id, "data": args.data or "", "count": args.count,
            "interval": args.interval}
    return _out(_req(args, "POST", "/api/send", body), args)


def cmd_frames(args) -> int:
    try:
        from websockets.sync.client import connect as ws_connect
    except ImportError:
        return _out({"ok": False, "error": "brak pakietu websockets "
                                           "(py -m pip install websockets)"}, args, 1)
    ws_url = (args.url.replace("https://", "wss://").replace("http://", "ws://")
              .rstrip("/") + "/ws")
    end = time.monotonic() + args.seconds
    count = 0
    try:
        with ws_connect(ws_url, open_timeout=5) as ws:
            while time.monotonic() < end:
                try:
                    raw = ws.recv(timeout=min(0.5, max(0.02, end - time.monotonic())))
                except TimeoutError:
                    continue
                try:
                    msg = json.loads(raw)
                except Exception:  # noqa: BLE001
                    continue
                if msg.get("type") != "update":
                    continue
                for f in msg.get("frames", []):
                    _dump({"t": f.get("t"), "id": f.get("id"), "x": f.get("x", 0),
                           "d": f.get("d"), "n": f.get("n", "")}, False)
                    count += 1
                    if args.max and count >= args.max:
                        break
                if args.max and count >= args.max:
                    break
    except Exception as exc:  # noqa: BLE001
        _dump({"ok": False, "error": f"WS: {exc}"}, getattr(args, "pretty", False))
        return 2
    if args.summary:
        _dump({"ok": True, "frames": count, "seconds": args.seconds},
              getattr(args, "pretty", False))
    return 0


def cmd_dbc_list(args) -> int:
    return _out(_req(args, "GET", "/api/dbc/list"), args)


def cmd_dbc_load(args) -> int:
    return _out(_req(args, "POST", "/api/dbc/load", {"path": args.path}), args)


def cmd_uds_scan(args) -> int:
    body = {"ids": args.ids, "offset": args.offset, "timeout_ms": args.timeout_ms}
    return _out(_req(args, "POST", "/api/uds/scan", body), args)


def cmd_uds_read(args) -> int:
    tx, rx = _ids_pair(args)
    dids = [d.strip() for d in str(args.dids).split(",") if d.strip()]
    body = {"txid": f"{tx:X}", "rxid": f"{rx:X}", "dids": dids,
            "session": args.session}
    return _out(_req(args, "POST", "/api/uds/read", body), args)


def cmd_uds_dtc(args) -> int:
    tx, rx = _ids_pair(args)
    body = {"txid": f"{tx:X}", "rxid": f"{rx:X}", "session": args.session,
            "mask": args.mask, "clear": args.clear, "confirm": args.confirm}
    return _out(_req(args, "POST", "/api/uds/dtc", body), args)


def cmd_log_stats(args) -> int:
    return _out(_req(args, "POST", "/api/log/stats", {"file": args.file}), args)


def cmd_log_trim(args) -> int:
    body = {"file": args.file, "from_s": args.from_s, "to_s": args.to_s,
            "offset": args.offset, "count": args.count}
    return _out(_req(args, "POST", "/api/log/trim", body), args)


def cmd_replay_start(args) -> int:
    rules = json.loads(args.rules) if args.rules else {}
    body = {"file": args.file, "rate": args.rate, "loop": args.loop,
            "limit": args.limit, "rules": rules}
    return _out(_req(args, "POST", "/api/log/replay/start", body), args)


def cmd_replay_stop(args) -> int:
    return _out(_req(args, "POST", "/api/log/replay/stop", {}), args)


def cmd_annotate(args) -> int:
    key = args.key if args.key is not None else key_of(args.id, args.ext)
    body = {"key": key, "name": args.name or "", "note": args.note or ""}
    return _out(_req(args, "POST", "/api/annotation", body), args)


def cmd_profiles(args) -> int:
    return _out(_req(args, "GET", "/api/profiles"), args)


def cmd_profile_load(args) -> int:
    return _out(_req(args, "POST", "/api/profile/load", {"name": args.name}), args)


def cmd_trigger_arm(args) -> int:
    key = args.key if args.key is not None else key_of(args.id, args.ext)
    body = {"key": key, "byte": args.byte, "pre": args.pre, "post": args.post,
            "keep": args.keep}
    return _out(_req(args, "POST", "/api/trigger/arm", body), args)


def cmd_trigger_disarm(args) -> int:
    return _out(_req(args, "POST", "/api/trigger/disarm", {}), args)


def cmd_call(args) -> int:
    try:
        body = json.loads(args.body) if args.body else None
    except ValueError as exc:
        print(f"# Zly JSON w --body: {exc}", file=sys.stderr)
        return 2
    res = _req(args, args.method, args.path, body)
    return _out(res, args)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _sp(sub, name, helptext, fn):
    p = sub.add_parser(name, help=helptext)
    p.set_defaults(_fn=fn)
    return p


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", default=DEFAULT_URL,
                        help=f"adres serwera Studia (domyślnie {DEFAULT_URL})")
    parser.add_argument("--pretty", action="store_true", help="czytelny JSON (wcięcia)")
    parser.add_argument("--timeout", type=float, default=120.0,
                        help="timeout HTTP [s] (domyślnie 120)")
    sub = parser.add_subparsers(dest="cmd", metavar="<komenda>")

    _sp(sub, "status", "status sesji (JSON)", cmd_status)
    _sp(sub, "ports", "lista portów COM z serwera", cmd_ports)

    p = _sp(sub, "connect", "połącz magistralę", cmd_connect)
    p.add_argument("--interface", "-i", default="slcan")
    p.add_argument("--port", "-c")
    p.add_argument("--bitrate", "-b", type=int, default=500000)
    p.add_argument("--silent", action="store_true")
    p.add_argument("--demo", action="store_true", help="generator demo")

    _sp(sub, "disconnect", "rozłącz", cmd_disconnect)

    p = _sp(sub, "send", "wyślij ramkę", cmd_send)
    p.add_argument("--id", required=True)
    p.add_argument("--data", default="")
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--interval", type=float, default=0.1)

    p = _sp(sub, "frames", "strumień ramek (JSONL) z WebSocket", cmd_frames)
    p.add_argument("--seconds", type=float, default=5.0)
    p.add_argument("--max", type=int, default=0, help="limit ramek (0 = bez limitu)")
    p.add_argument("--summary", action="store_true", help="dodaj podsumowanie na końcu")

    _sp(sub, "dbc-list", "lista baz DBC", cmd_dbc_list)
    p = _sp(sub, "dbc-load", "wczytaj bazę DBC", cmd_dbc_load)
    p.add_argument("--path", required=True)

    p = _sp(sub, "uds-scan", "skaner ECU (UDS)", cmd_uds_scan)
    p.add_argument("--ids", default="600-6FF")
    p.add_argument("--offset", type=int, default=8)
    p.add_argument("--timeout-ms", type=float, default=50.0)

    p = _sp(sub, "uds-read", "odczyt DID (UDS)", cmd_uds_read)
    p.add_argument("--txid", required=True)
    p.add_argument("--rxid")
    p.add_argument("--dids", default="F190")
    p.add_argument("--session")

    p = _sp(sub, "uds-dtc", "kody DTC (UDS)", cmd_uds_dtc)
    p.add_argument("--txid", required=True)
    p.add_argument("--rxid")
    p.add_argument("--session")
    p.add_argument("--mask", default="FF")
    p.add_argument("--clear", action="store_true")
    p.add_argument("--confirm", action="store_true")

    p = _sp(sub, "log-stats", "statystyki logu", cmd_log_stats)
    p.add_argument("--file", required=True)

    p = _sp(sub, "log-trim", "przytnij log", cmd_log_trim)
    p.add_argument("--file", required=True)
    p.add_argument("--from", dest="from_s", type=float, default=None)
    p.add_argument("--to", dest="to_s", type=float, default=None)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--count", type=int, default=0)

    p = _sp(sub, "replay-start", "odtwarzanie logu (z modyfikacją)", cmd_replay_start)
    p.add_argument("--file", required=True)
    p.add_argument("--rate", type=float, default=1.0)
    p.add_argument("--loop", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--rules", help="reguły JSON, np. '{\"set\":[...]}'")

    _sp(sub, "replay-stop", "zatrzymaj odtwarzanie", cmd_replay_stop)

    p = _sp(sub, "annotate", "anotacja ID (nazwa/notatka)", cmd_annotate)
    p.add_argument("--id", type=int, default=0, help="ID w formie dziesiętnej (0x130 -> 304)")
    p.add_argument("--ext", action="store_true")
    p.add_argument("--key", type=int, default=None, help="klucz globalny (zamiast --id)")
    p.add_argument("--name")
    p.add_argument("--note")

    _sp(sub, "profiles", "lista profili pojazdów", cmd_profiles)
    p = _sp(sub, "profile-load", "wczytaj profil (anotacje)", cmd_profile_load)
    p.add_argument("--name", required=True)

    p = _sp(sub, "trigger-arm", "uzbrój trigger ±s", cmd_trigger_arm)
    p.add_argument("--id", type=int, default=0)
    p.add_argument("--ext", action="store_true")
    p.add_argument("--key", type=int, default=None)
    p.add_argument("--byte", type=int, default=0)
    p.add_argument("--pre", type=float, default=5.0)
    p.add_argument("--post", type=float, default=5.0)
    p.add_argument("--keep", action="store_true")

    _sp(sub, "trigger-disarm", "rozbrój trigger", cmd_trigger_disarm)

    p = _sp(sub, "call", "dowolne wywołanie REST", cmd_call)
    p.add_argument("path", help="ścieżka API, np. /api/status")
    p.add_argument("--method", default="GET", choices=("GET", "POST"))
    p.add_argument("--body", help="treść JSON dla POST")


def run(args) -> int:
    fn = getattr(args, "_fn", None)
    if fn is None:
        print("Użyj: py -m canstudio ctl <komenda> …  (py -m canstudio ctl -h)")
        return 1
    return fn(args) or 0
