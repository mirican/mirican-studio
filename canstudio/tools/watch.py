"""Narzędzie: watch — nasłuch z automatyczną detekcją interesujących zmian."""

from __future__ import annotations

import argparse
import datetime
import os
import time

from ..bus import add_bus_args, open_bus
from ..detect import ChangeDetector
from ..frames import format_frame, parse_ids
from ..stats import IdStats

NAME = "watch"
HELP = "Nasłuch z automatyczną detekcją zmian (przyciski, flagi, zdarzenia)"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    add_bus_args(parser)
    parser.add_argument("--profile", help="profil pojazdu z profiles/ (np. bmw)")
    parser.add_argument("--min-stable", type=int, default=20,
                        help="bajt musi być stabilny przez N ramek, by zgłosić zmianę (0 = zgłaszaj wszystkie)")
    parser.add_argument("--min-gap", type=float, default=0.15,
                        help="min. odstęp między raportami dla tego samego bajtu [s]")
    parser.add_argument("--ids", help="filtruj ID, np. 0x123,0x456")
    parser.add_argument("--hide-ids", help="ukryj ID (np. 0x7DF,0x7E8)")
    parser.add_argument("--duration", type=float, default=0.0, help="czas nasłuchu w s [0 = bez limitu]")
    parser.add_argument("--count", type=int, default=0, help="zakończ po N ramkach")
    parser.add_argument("--active", action="store_true",
                        help="tryb normalny zamiast biernego (watch domyślnie działa w silent)")
    parser.add_argument("--quiet-new", action="store_true", help="nie pokazuj komunikatów o nowych ID")
    parser.add_argument("--log-dir", default=None, help="katalog na logi (domyślnie logs/)")
    parser.add_argument("--no-log", action="store_true", help="nie zapisuj logu")


def run(args) -> int:
    args.silent = not args.active  # watch domyślnie bierny
    ids = parse_ids(args.ids) if args.ids else None
    hide = parse_ids(args.hide_ids) if args.hide_ids else set()

    log_handle = None
    if not args.no_log:
        os.makedirs(args.log_dir, exist_ok=True)
        fname = "watch_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".log"
        path = os.path.join(args.log_dir, fname)
        log_handle = open(path, "w", encoding="utf-8", buffering=1)
        print(f"# log: {path}")

    bus = open_bus(args)
    print(f"# watch: {args.interface}:{args.channel} @ {args.bitrate} bit/s"
          + ("  [silent]" if args.silent else "")
          + f"  min_stable={args.min_stable}  (Ctrl+C kończy)")

    detector = ChangeDetector(min_stable=args.min_stable, min_gap_s=args.min_gap)
    stats = IdStats()
    events_count = 0
    t0 = None
    t_start = time.monotonic()
    try:
        while True:
            if args.duration and (time.monotonic() - t_start) >= args.duration:
                break
            msg = bus.recv(timeout=0.5)
            if msg is None:
                continue
            if ids is not None and msg.arbitration_id not in ids:
                continue
            if msg.arbitration_id in hide:
                continue
            stats.add(msg.arbitration_id, msg.timestamp, msg.data)
            if log_handle is not None:
                log_handle.write(format_frame(msg, args.channel or args.interface) + "\n")
            if t0 is None:
                t0 = msg.timestamp

            for ev in detector.feed(msg.arbitration_id, bytes(msg.data), msg.timestamp):
                events_count += 1
                if ev.byte < 0:
                    if not args.quiet_new:
                        print(f"# NOWE ID 0x{ev.arbitration_id:03X} (dlc={len(msg.data)})")
                    if log_handle:
                        log_handle.write(
                            f"# EVENT {msg.timestamp:.6f} NOWE_ID 0x{ev.arbitration_id:03X}\n")
                else:
                    rel = msg.timestamp - t0
                    print(f"# EVENT {rel:8.3f}s  0x{ev.arbitration_id:03X} b{ev.byte}: "
                          f"{ev.old:02X} -> {ev.new:02X}   "
                          f"(stabilny {ev.stable_frames} ramek, zmian: {ev.changes_total})")
                    if log_handle:
                        log_handle.write(
                            f"# EVENT {msg.timestamp:.6f} 0x{ev.arbitration_id:03X} "
                            f"b{ev.byte} {ev.old:02X}->{ev.new:02X}\n")
            if args.count and stats.total >= args.count:
                break
    except KeyboardInterrupt:
        print("\n# przerwano (Ctrl+C)")
    finally:
        bus.shutdown()
        if log_handle is not None:
            log_handle.close()

    print(f"# ramek: {stats.total}, unikalnych ID: {len(stats.counts)}, zdarzeń: {events_count}")
    rows = detector.interesting_bytes(15)
    if rows:
        print("# najbardziej 'zdarzeniowe' bajty (mało zmian przy wielu ramkach):")
        for aid, byte, changes, frames, _rate in rows[:10]:
            per = stats.period(aid)
            extra = f", ~{per * 1000:.1f} ms" if per else ""
            print(f"#   0x{aid:03X} b{byte}: zmian {changes} / {frames} ramek{extra}")
    return 0
