"""Narzędzie: sniff — nasłuch magistrali CAN z logiem i dekodowaniem DBC.

Przykłady:
  py -m canstudio sniff --channel COM7               # 500 kbit/s, log do logs/
  py -m canstudio sniff --channel COM7 --silent      # nasłuch bez ACK (canable2: M1)
  py -m canstudio sniff --channel COM7 --marks       # znaczniki: ENTER / tekst+ENTER
  py -m canstudio sniff --channel COM7 --dbc dbc/opendbc/bmw_e9x_e8x.dbc
  py -m canstudio sniff --channel COM7 --ids 0x130,0x1A0 --duration 60
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
import threading
import time

from ..bus import add_bus_args, open_bus, serial_ports
from ..config import resolve_path
from ..dbc import decode_into, load_dbc
from ..frames import format_frame, parse_ids
from ..json_cli import add_json_args, emit, emitl, json_mode
from ..stats import IdStats

NAME = "sniff"
HELP = "Nasłuch CAN (zapis candump + opcjonalne dekodowanie DBC)"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    add_bus_args(parser)
    parser.add_argument("--profile", help="profil pojazdu z profiles/ (np. bmw)")
    parser.add_argument("--dbc", help="plik .dbc do dekodowania ramek na żywo")
    parser.add_argument("--ids", help="filtruj ID, np. 0x123,0x456 (hex/dec)")
    parser.add_argument("--hide-ids", help="ukryj ID (np. 0x7DF,0x7E8)")
    parser.add_argument("--duration", type=float, default=0.0, help="czas nasłuchu w s [0 = bez limitu]")
    parser.add_argument("--count", type=int, default=0, help="zakończ po N zapisanych ramkach")
    parser.add_argument("--log-dir", default=None, help="katalog na logi (domyślnie logs/)")
    parser.add_argument("--no-log", action="store_true", help="nie zapisuj logu")
    parser.add_argument("--quiet", "-q", action="store_true", help="nie drukuj ramek na żywo")
    parser.add_argument("--marks", action="store_true",
                        help="znaczniki z klawiatury: ENTER = znacznik, tekst+ENTER = etykieta "
                             "(np. 'przycisk szyby'); zapisywane do logu")
    parser.add_argument("--list-ports", action="store_true", help="pokaż porty COM i wyjdź")
    add_json_args(parser, jsonl=True)


def _start_marker_reader(markers: list, log_handle) -> None:
    """Czyta stdin: ENTER = znacznik, tekst+ENTER = etykieta. Zapisuje do logu."""

    def worker():
        count = 0
        saw_input = False
        try:
            for line in sys.stdin:
                saw_input = True
                label = line.strip() or f"mark_{count}"
                count += 1
                ts = time.time()
                markers.append((ts, label))
                if log_handle is not None:
                    log_handle.write(f"# MARK {ts:.6f} {label}\n")
                print(f"\n# MARK {label} @ {ts:.6f}")
        except Exception:
            pass
        if not saw_input:
            print("\n# (stdin zamknięty - znaczniki wyłączone)")

    threading.Thread(target=worker, daemon=True).start()


def run(args) -> int:
    if args.list_ports:
        for port in serial_ports():
            vidpid = f"{port.vid:04X}:{port.pid:04X}" if port.vid else "-"
            print(f"{port.device:10s}  {vidpid:10s}  {port.description}")
        return 0

    json_mode(args)
    ids = parse_ids(args.ids) if args.ids else None
    hide = parse_ids(args.hide_ids) if args.hide_ids else set()
    db = load_dbc(resolve_path(args.dbc)) if args.dbc else None

    log_handle = None
    log_path = None
    if not args.no_log:
        os.makedirs(args.log_dir, exist_ok=True)
        fname = "sniff_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".log"
        path = os.path.join(args.log_dir, fname)
        log_handle = open(path, "w", encoding="utf-8", buffering=1)
        log_path = path
        print(f"# log: {path}")

    profile = getattr(args, "_profile", None)
    if profile:
        print(f"# profil: {profile.get('name')} — {profile.get('description', '')}")

    markers: list = []
    if args.marks:
        _start_marker_reader(markers, log_handle)
        print("# znaczniki: ENTER = marker, tekst + ENTER = etykieta")
        if args.no_log:
            print("# uwaga: --marks bez logu - znaczniki nie będą zapisane")

    bus = open_bus(args)
    print(f"# nasłuch: {args.interface}:{args.channel} @ {args.bitrate} bit/s"
          + ("  [silent]" if args.silent else "")
          + "  (Ctrl+C aby zakończyć)")

    stats = IdStats()
    t0 = time.monotonic()
    try:
        while True:
            if args.duration and (time.monotonic() - t0) >= args.duration:
                break
            msg = bus.recv(timeout=0.5)
            if msg is None:
                continue
            if ids is not None and msg.arbitration_id not in ids:
                continue
            if msg.arbitration_id in hide:
                continue
            line = format_frame(msg, args.channel or args.interface)
            if log_handle is not None:
                log_handle.write(line + "\n")
            stats.add(msg.arbitration_id, msg.timestamp, msg.data)
            if getattr(args, "jsonl", False):
                item = {"t": round(msg.timestamp or 0, 6), "id": msg.arbitration_id,
                        "x": 1 if msg.is_extended_id else 0,
                        "d": bytes(msg.data).hex().upper()}
                if db is not None:
                    decoded = decode_into(db, msg)
                    if decoded:
                        item["dec"] = decoded
                emitl(item)
            if not args.quiet:
                extra = ""
                if db is not None:
                    decoded = decode_into(db, msg)
                    if decoded:
                        extra = "  -> " + ", ".join(
                            f"{k}={v}" for k, v in list(decoded.items())[:8])
                print(line + extra)
            if args.count and stats.total >= args.count:
                break
    except KeyboardInterrupt:
        print("\n# przerwano (Ctrl+C)")
    finally:
        bus.shutdown()
        if log_handle is not None:
            log_handle.close()

    if args.marks:
        print(f"# znaczników: {len(markers)}")
    print(f"# ramek: {stats.total}, unikalnych ID: {len(stats.counts)}")
    if stats.total:
        print("# najczęstsze ID:")
        for aid, cnt in stats.top(10):
            per = stats.period(aid)
            extra = f"  @ ~{per * 1000:.1f} ms" if per else ""
            print(f"#   0x{aid:03X}  x{cnt}{extra}")
    if getattr(args, "json", False):
        emit({"ok": True, "interface": args.interface, "channel": args.channel,
              "bitrate": args.bitrate, "frames": stats.total,
              "ids": [{"id": aid, "count": cnt, "period": stats.period(aid)}
                      for aid, cnt in stats.top(500)],
              "log": log_path})
    return 0
