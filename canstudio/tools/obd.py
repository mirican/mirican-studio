"""Narzedzie: obd - diagnostyka OBD-II przez adapter ELM327 (np. vLinker MS).

Przyklady:
  py -m canstudio obd test                          # test lacza (auto-port)
  py -m canstudio obd test --port COM8
  py -m canstudio obd info                          # VIN + wspierane PID-y
  py -m canstudio obd read 010C 010D 0105           # jednorazowy odczyt
  py -m canstudio obd monitor --pids 010C,010D --interval 0.3
  py -m canstudio obd monitor --pids 010C,010D --save
  py -m canstudio obd dtc                           # odczyt kodow bledow
  py -m canstudio obd dtc --clear --yes             # kasowanie DTC (postoj!)

Uwaga: odczyt PID/DTC/VIN wymaga ZAPLONU (magistrala aktywna). vLinker MS
laczy sie po klasycznym BT (SPP -> COMx); telefon nie moze go trzymac
(jedno polaczenie naraz). To nie jest sniff CAN - do nasluchu sluzy Canable.
"""

from __future__ import annotations

import argparse
import time

from ..elm327 import Elm327, find_elm_port
from ..json_cli import add_json_args, emit, emitl, json_mode
from ..obd import (clear_dtc, norm_pid, pid_name, read_dtc, read_pids,
                   read_supported, read_vin)
from ..obd_log import SessionWriter
from ..vin import decode_vin

NAME = "obd"
HELP = "Diagnostyka OBD-II przez ELM327 (vLinker MS): PID-y, DTC, VIN"


# ---------------------------------------------------------------------------
# Wspolne
# ---------------------------------------------------------------------------

def _add_conn_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("polaczenie (adapter ELM327)")
    g.add_argument("--port", help="port COM (domyslnie: auto-wykrycie vLinkera)")
    g.add_argument("--baud", type=int, default=115200, help="predkosc portu (domyslnie 115200)")
    g.add_argument("--timeout", type=float, default=3.0, help="timeout komendy [s]")


def _open_elm(args):
    """Otwiera adapter; zwraca (elm, port, powod) albo (None, None, komunikat)."""
    if args.port:
        port, why = args.port, "z --port"
    else:
        port, why = find_elm_port()
    if not port:
        return None, None, "Nie znaleziono portu adaptera ELM (vLinker) - podaj --port COMx"
    elm = Elm327(port, baud=args.baud, timeout=args.timeout)
    try:
        elm.open()
    except Exception as exc:  # noqa: BLE001
        return None, None, f"Nie moge otworzyc {port}: {exc}"
    return elm, port, why


def _ts() -> str:
    return time.strftime("%H:%M:%S") + f".{int(time.time() % 1 * 1000):03d}"


def _warmup(elm, timeout: float = 25.0) -> str:
    """Dogrzanie po ATZ: pierwsze zadanie moze trwac dlugo (adapter szuka
    protokolu w trybie ATSP0). Robimy je raz na sesje, z duzym zapasem czasu."""
    return elm.obd("0100", timeout=timeout)


def _bus_down(resp: str) -> bool:
    u = (resp or "").upper().replace(" ", "")
    return "UNABLETOCONNECT" in u and "4100" not in u


def _parse_pids(spec) -> list:
    """['010C','010D'] / '010C,010D' / '010C 010D' (PowerShell!) -> [0x0C, 0x0D]."""
    if isinstance(spec, str):
        items = [spec]
    else:
        items = list(spec)
    parts = []
    for it in items:
        parts.extend(p for p in str(it).replace(";", ",").split(",") if p.strip())
    return [norm_pid(x) for x in parts]


# ---------------------------------------------------------------------------
# test
# ---------------------------------------------------------------------------

def cmd_test(args) -> int:
    json_mode(args)
    elm, port, why = _open_elm(args)
    if elm is None:
        if getattr(args, "json", False):
            emit({"ok": False, "error": why})
        else:
            print(f"# {why}")
        return 1
    try:
        info = elm.init()
        probe = elm.probe_bus(timeout=args.probe_timeout)
        from ..obd import parse_voltage
        adapter = (info.get("adapter") or "").strip().splitlines()
        adapter = adapter[-1] if adapter else "?"
        volt = parse_voltage(info.get("voltage", ""))
        if getattr(args, "json", False):
            emit({"ok": True, "port": port, "why": why, "adapter": adapter,
                  "voltage_v": volt, "bus": probe["bus"], "probe_raw": probe["raw"]})
        else:
            print(f"# port: {port} ({why})")
            print(f"# adapter: {adapter}")
            print(f"# napiecie: {volt if volt is not None else '?'} V")
            if probe["bus"]:
                print("# magistrala: OK - ECU odpowiada")
            else:
                print("# magistrala: brak odpowiedzi - sprawdz ZAPLON (IGN ON)")
                print("#   (jesli SEARCHING.../'UNABLE TO CONNECT' przy wlaczonym zaplonie -")
                print("#    sprawdz, czy telefon nie trzyma adaptera i czy auto ma CAN 500k)")
        return 0
    finally:
        elm.close()


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------

def cmd_info(args) -> int:
    json_mode(args)
    elm, port, why = _open_elm(args)
    if elm is None:
        if getattr(args, "json", False):
            emit({"ok": False, "error": why})
        else:
            print(f"# {why}")
        return 1
    try:
        elm.init()
        warm = _warmup(elm)
        if _bus_down(warm):
            vin, supported = None, []
        else:
            vin = read_vin(elm)
            supported = read_supported(elm)
        vin_dec = decode_vin(vin) if vin else None
        if getattr(args, "json", False):
            emit({"ok": True, "port": port, "vin": vin, "vin_info": vin_dec,
                  "supported": supported, "count": len(supported)})
        else:
            print(f"# port: {port} ({why})")
            print(f"# VIN: {vin or '(brak odpowiedzi - zaplon ON?)'}")
            if vin_dec and vin_dec.get("ok"):
                if vin_dec.get("brand"):
                    print(f"#   marka: {vin_dec['brand']}"
                          + (f" ({vin_dec['country']})" if vin_dec.get("country") else ""))
                if vin_dec.get("model") and vin_dec["model"].get("name"):
                    print(f"#   model: {vin_dec['model']['name']} (kod {vin_dec['model']['code']})")
                if vin_dec.get("engine"):
                    print(f"#   silnik: {vin_dec['engine']['name']} (kod {vin_dec['engine']['code']})")
                if vin_dec.get("platform"):
                    print(f"#   platforma: {vin_dec['platform']['name']} ({vin_dec['platform']['code']})")
                if vin_dec.get("year_likely"):
                    print(f"#   rok: {vin_dec['year_likely']}")
            if supported:
                print(f"# wspierane PID-y: {len(supported)}")
                names = ", ".join(f"01{p:02X}({pid_name(p)})" for p in supported[:12])
                print(f"#   {names}{' ...' if len(supported) > 12 else ''}")
            else:
                print("# wspierane PID-y: brak odpowiedzi magistrali")
        return 0 if (vin or supported) else 2
    finally:
        elm.close()


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------

def cmd_read(args) -> int:
    json_mode(args)
    try:
        pids = _parse_pids(args.pids or ["010C", "010D", "0105", "012F"])
    except ValueError as exc:
        print(f"# zly PID: {exc}")
        return 1
    elm, port, why = _open_elm(args)
    if elm is None:
        if getattr(args, "json", False):
            emit({"ok": False, "error": why})
        else:
            print(f"# {why}")
        return 1
    try:
        elm.init()
        warm = _warmup(elm)
        if _bus_down(warm):
            if getattr(args, "json", False):
                emit({"ok": False, "error": "brak odpowiedzi magistrali (zaplon ON?)", "port": port})
            else:
                print("# Magistrala nie odpowiada - sprawdz zaplon (IGN ON).")
            return 2
        rows = read_pids(elm, pids, timeout=args.timeout)
        ok = [r for r in rows if r["status"] == "ok"]
        if getattr(args, "json", False):
            emit({"ok": bool(ok), "port": port, "rows": rows})
        else:
            print(f"# odczyt PID-ow ({port}):")
            for r in rows:
                if r["status"] == "ok":
                    print(f"  {r['pid']}  {r['name']:<18} {r['value']:>10} {r['unit']}")
                elif r["status"] == "nodata":
                    print(f"  {r['pid']}  {r['name']:<18} {'-':>10} (brak danych / niewspierany)")
                else:
                    print(f"  {r['pid']}  {r['name']:<18} {'-':>10} (brak odpowiedzi magistrali)")
            if not ok:
                print("# Brak danych - sprawdz zaplon (IGN ON) i polaczenie z adapterem.")
        return 0 if ok else 2
    finally:
        elm.close()


# ---------------------------------------------------------------------------
# monitor
# ---------------------------------------------------------------------------

def cmd_monitor(args) -> int:
    json_mode(args)
    try:
        pids = _parse_pids(args.pids)
    except ValueError as exc:
        print(f"# zly PID: {exc}")
        return 1
    elm, port, why = _open_elm(args)
    if elm is None:
        if getattr(args, "json", False) or getattr(args, "jsonl", False):
            emit({"ok": False, "error": why})
        else:
            print(f"# {why}")
        return 1
    writer = None
    save_path = None
    rounds = 0
    try:
        elm.init()
        warm = _warmup(elm)
        if _bus_down(warm):
            if getattr(args, "jsonl", False):
                emit({"ok": False, "error": "brak odpowiedzi magistrali (zaplon ON?)"})
            elif not getattr(args, "json", False):
                print("# Magistrala nie odpowiada - sprawdz zaplon (IGN ON).")
            return 2
        if args.save:
            writer = SessionWriter(adapter="vLinker MS (ELM327)",
                                   pids=[f"01{p:02X}" for p in pids])
            save_path = writer.path
        if not getattr(args, "jsonl", False):
            print(f"# monitor OBD ({port}) - Ctrl+C aby zakonczyc"
                  + (f" - zapis: {save_path}" if save_path else ""))
        t0 = time.monotonic()
        while True:
            if args.duration and (time.monotonic() - t0) >= args.duration:
                break
            rounds += 1
            rows = read_pids(elm, pids, timeout=args.timeout)
            for r in rows:
                if getattr(args, "jsonl", False):
                    emitl({"t": round(time.time(), 3), "pid": r["pid"], "name": r["name"],
                           "value": r["value"], "unit": r["unit"], "status": r["status"]})
                elif r["status"] == "ok":
                    print(f"{_ts()}  {r['pid']}  {r['name']:<18} {r['value']:>10} {r['unit']}")
                else:
                    print(f"{_ts()}  {r['pid']}  {r['name']:<18} {'-':>10} ({r['status']})")
                if writer is not None and r["status"] == "ok":
                    writer.pid(r["pid"], r["name"], r["value"], r["unit"])
            time.sleep(max(0.05, args.interval))
    except KeyboardInterrupt:
        print("\n# przerwano (Ctrl+C)")
    finally:
        if writer is not None:
            writer.close()
        elm.close()
    if getattr(args, "jsonl", False):
        emitl({"kind": "summary", "rounds": rounds, "saved": str(save_path) if save_path else None})
    else:
        print(f"# rund: {rounds}" + (f"; zapisano: {save_path}" if save_path else ""))
    return 0


# ---------------------------------------------------------------------------
# dtc
# ---------------------------------------------------------------------------

def cmd_dtc(args) -> int:
    json_mode(args)
    if args.clear and not args.yes:
        msg = "Kasowanie DTC wymaga --yes (operacja modyfikujaca; tylko postoj!)"
        if getattr(args, "json", False):
            emit({"ok": False, "error": msg})
        else:
            print(f"# {msg}")
        return 1
    elm, port, why = _open_elm(args)
    if elm is None:
        if getattr(args, "json", False):
            emit({"ok": False, "error": why})
        else:
            print(f"# {why}")
        return 1
    try:
        elm.init()
        warm = _warmup(elm)
        if _bus_down(warm):
            codes, dtc_raw = [], warm
        else:
            codes, dtc_raw = read_dtc(elm)
        cleared = None
        if args.clear:
            resp = clear_dtc(elm)
            cleared = ("44" in resp) or ("OK" in resp.upper())
        if getattr(args, "json", False):
            emit({"ok": True, "port": port, "codes": codes, "count": len(codes),
                  "cleared": cleared})
        else:
            print(f"# DTC ({port}): {len(codes)} kod(ow)")
            for c in codes:
                print(f"  {c}")
            if not codes:
                if "43" in dtc_raw:
                    print("#   brak kodow (ECU odpowiedzialo)")
                else:
                    print("#   brak odpowiedzi magistrali - sprawdz zaplon (IGN ON)")
            if args.clear:
                print("# kasowanie DTC: " + ("OK" if cleared else "brak potwierdzenia '44'"))
        return 0
    finally:
        elm.close()


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------

def add_arguments(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="tryb", metavar="<tryb>")

    p = sub.add_parser("test", help="test lacza z adapterem i magistrala")
    _add_conn_args(p)
    p.add_argument("--probe-timeout", type=float, default=20.0,
                   help="ile czekac na odpowiedz magistrali przy probie 0100 [s]")
    add_json_args(p)
    p.set_defaults(_cmd=cmd_test)

    p = sub.add_parser("info", help="VIN + lista wspieranych PID-ow")
    _add_conn_args(p)
    add_json_args(p)
    p.set_defaults(_cmd=cmd_info)

    p = sub.add_parser("read", help="jednorazowy odczyt PID-ow")
    p.add_argument("pids", nargs="*", help="PID-y (np. 010C 010D albo 0C,0D); domyslnie zestaw podstawowy")
    _add_conn_args(p)
    add_json_args(p)
    p.set_defaults(_cmd=cmd_read)

    p = sub.add_parser("monitor", help="ciagly odczyt PID-ow (live)")
    p.add_argument("--pids", nargs="+", default="010C,010D,0105,012F",
                   help="lista PID-ow (domyslnie 010C,010D,0105,012F); przecinki lub spacje")
    p.add_argument("--interval", type=float, default=0.3, help="odstep miedzy rundami [s]")
    p.add_argument("--duration", type=float, default=0.0, help="czas trwania [s; 0 = bez limitu]")
    p.add_argument("--save", action="store_true", help="zapis do logs/obd_<ts>.jsonl (format obd-logger/1)")
    _add_conn_args(p)
    add_json_args(p, jsonl=True)
    p.set_defaults(_cmd=cmd_monitor)

    p = sub.add_parser("dtc", help="odczyt / kasowanie kodow bledow")
    p.add_argument("--clear", action="store_true", help="skasuj DTC (tryb 04)")
    p.add_argument("--yes", action="store_true", help="potwierdzenie kasowania")
    _add_conn_args(p)
    add_json_args(p)
    p.set_defaults(_cmd=cmd_dtc)


def run(args) -> int:
    fn = getattr(args, "_cmd", None)
    if fn is None:
        print("Uzyj: py -m canstudio obd {test|info|read|monitor|dtc} ...")
        return 1
    return fn(args)
