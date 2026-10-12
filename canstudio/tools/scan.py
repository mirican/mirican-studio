"""Narzędzie: scan — skaner prędkości magistrali (auto-detekcja bitrate)."""

from __future__ import annotations

import argparse
import time

from ..bus import add_bus_args, open_bus
from ..json_cli import add_json_args, emit, json_mode
from ..stats import IdStats

NAME = "scan"
HELP = "Skaner prędkości magistrali (nasłuch po kolei na typowych bitrate)"
DEFAULT_RATES = "1000000,500000,250000,125000,100000,83300,50000"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    add_bus_args(parser)
    parser.add_argument("--profile", help="profil pojazdu z profiles/ (np. bmw)")
    parser.add_argument("--rates", default=DEFAULT_RATES,
                        help=f"lista prędkości do sprawdzenia (domyślnie {DEFAULT_RATES})")
    parser.add_argument("--per-rate", type=float, default=1.0,
                        help="czas nasłuchu na każdą prędkość [s]")
    parser.add_argument("--active", action="store_true",
                        help="tryb normalny zamiast biernego (skan domyślnie działa w silent)")
    add_json_args(parser)


def run(args) -> int:
    json_mode(args)
    rates = [int(x) for x in args.rates.replace(";", ",").split(",") if x.strip()]
    args.silent = not args.active  # skan domyślnie wykonujemy biernie

    print(f"# skan bitrate: {len(rates)} prędkości x {args.per_rate}s "
          f"({args.interface}:{args.channel})")
    best = None
    results = []
    for rate in rates:
        args.bitrate = rate
        stats = IdStats()
        try:
            bus = open_bus(args)
        except Exception as exc:  # noqa: BLE001 - raportujemy i lecimy dalej
            print(f"# {rate:>7} bit/s: BŁĄD otwarcia: {exc}")
            continue
        try:
            t_end = time.monotonic() + args.per_rate
            while time.monotonic() < t_end and stats.total < 5000:
                msg = bus.recv(timeout=0.2)
                if msg is not None:
                    stats.add(msg.arbitration_id, msg.timestamp, msg.data)
        finally:
            bus.shutdown()

        if stats.total and (best is None or stats.total > best[1].total):
            best = (rate, stats)
        extra = ""
        if stats.total:
            top = ", ".join(f"0x{a:03X}" for a, _ in stats.top(3))
            extra = f", top: {top}"
        print(f"# {rate:>7} bit/s: {stats.total} ramek{extra}")
        results.append({"bitrate": rate, "frames": stats.total,
                        "unique_ids": len(stats.counts),
                        "top": [aid for aid, _ in stats.top(3)]})

    if getattr(args, "json", False):
        emit({"ok": True, "channel": args.channel, "rates": results,
              "best": best[0] if best is not None else None})
        return 0

    print()
    if best is not None:
        rate, stats = best
        print(f"# WYKRYTO RUCH: {rate} bit/s ({stats.total} ramek, "
              f"{len(stats.counts)} unikalnych ID)")
        print(f"# użyj: py -m canstudio sniff --channel {args.channel} --bitrate {rate}")
    else:
        print("# Brak ruchu na żadnej prędkości. Możliwe przyczyny:")
        print("#  - magistrala nieaktywna (auto uśpione / zapłon OFF)")
        print("#  - złe podłączenie (CAN-H/CAN-L) lub brak wspólnej masy")
        print("#  - prędkość inna niż na liście (podaj własną: --rates ...)")
    return 0
