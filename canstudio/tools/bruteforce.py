"""Narzędzie: bruteforce — (BENCH) przemiatanie ID / wartości / bitów.

Inspiracja: panel "CAN HACK / BruteForce" z analizatorów typu CAN SHARK:
wysyła serię prób (kolejne ID, kolejne wartości bajtu, kolejne bity) i po
każdej próbie nasłuchuje, czy coś odpowiedziało na magistrali.

⚠️ NARZĘDZIE WARSZTATOWE: nadaje na magistralę. Używaj wyłącznie na stole,
poza pojazdem w ruchu. Bez flagi --yes działa jako bezpieczny dry-run.
"""

from __future__ import annotations

import argparse
import datetime
import os
import time

import can

from ..bus import add_bus_args, open_bus
from ..frames import format_frame, parse_id

NAME = "bruteforce"
HELP = "(BENCH) Skaner: przemiatanie ID / wartości bajtu / bitów z nasłuchem reakcji"


def parse_values(spec: str):
    """'00-FF' (zakres) albo '01,02,03' (lista) -> lista wartości."""
    if not spec:
        return list(range(0x00, 0x100))
    if "-" in spec and "," not in spec:
        a, _, b = spec.partition("-")
        start, end = parse_id(a), parse_id(b)
        if start > end:
            start, end = end, start
        return list(range(start, end + 1))
    return [parse_id(x) for x in spec.replace(";", ",").split(",") if x.strip()]


def _build_probes(args):
    base = bytes.fromhex(args.data.replace(" ", "").replace("0x", "")) if args.data else bytes(8)
    probes = []

    if args.mode == "ids":
        start, end = parse_id(args.id_from), parse_id(args.id_to)
        for aid in range(start, end + 1, max(1, args.step)):
            probes.append((f"0x{aid:03X}", aid, bytes(base)))
        return probes

    if not args.arb_id:
        raise SystemExit(f"Tryb {args.mode} wymaga --id")
    aid = parse_id(args.arb_id)
    if len(base) <= args.byte:
        base = base + bytes(args.byte + 1 - len(base))

    if args.mode == "values":
        for value in parse_values(args.values):
            data = bytearray(base)
            data[args.byte] = value
            probes.append((f"val 0x{value:02X}", aid, bytes(data)))
    else:  # bits
        for bit in range(8):
            data = bytearray(base)
            data[args.byte] = (0xFF ^ (1 << bit)) if args.clear_bits else (1 << bit)
            probes.append((f"bit {bit} ({'0' if args.clear_bits else '1'})", aid, bytes(data)))
    return probes


def add_arguments(parser: argparse.ArgumentParser) -> None:
    add_bus_args(parser)
    parser.add_argument("--profile", help="profil pojazdu z profiles/ (np. bmw)")
    parser.add_argument("--mode", choices=("ids", "values", "bits"), default="ids",
                        help="ids = przemiatanie ID; values = wartości bajtu; bits = pojedyncze bity")
    parser.add_argument("--from", dest="id_from", default="0x000", help="ID od (tryb ids)")
    parser.add_argument("--to", dest="id_to", default="0x7FF", help="ID do (tryb ids)")
    parser.add_argument("--step", type=int, default=1, help="krok ID")
    parser.add_argument("--id", dest="arb_id", help="ID ramki (tryby values/bits)")
    parser.add_argument("--byte", type=int, default=0, help="indeks bajtu (tryby values/bits)")
    parser.add_argument("--values", help="'00-FF' albo lista '01,02,03' (tryb values)")
    parser.add_argument("--clear-bits", action="store_true",
                        help="tryb bits: zdejmuj bity z 0xFF zamiast ustawiać")
    parser.add_argument("--data", default="", help="szablon danych hex (domyślnie 8 zer)")
    parser.add_argument("--repeats", type=int, default=2, help="ile ramek na próbę")
    parser.add_argument("--interval", type=float, default=0.02, help="odstęp w serii [s]")
    parser.add_argument("--window-ms", type=int, default=40, help="nasłuch reakcji po próbie [ms]")
    parser.add_argument("--extended", action="store_true", help="ID rozszerzone")
    parser.add_argument("--yes", action="store_true",
                        help="POTWIERDZENIE: wykonaj nadawanie (bez tego tylko dry-run)")
    parser.add_argument("--log-dir", default=None, help="katalog na logi (domyślnie logs/)")
    parser.add_argument("--no-log", action="store_true", help="nie zapisuj logu")


def run(args) -> int:
    probes = _build_probes(args)
    if not probes:
        print("# brak prób")
        return 1
    if len(probes) > 20000:
        print("# Zbyt wiele prób (>20000) — zawęź zakres lub zwiększ --step.")
        return 1

    est = len(probes) * (max(1, args.repeats) * args.interval + args.window_ms / 1000.0 + 0.005)
    print(f"# plan: {len(probes)} prób, szacowany czas ~{est:.0f} s")
    if not args.yes:
        for label, aid, data in probes[:12]:
            print(f"#   {label}: id=0x{aid:03X} data={data.hex(' ').upper()}")
        if len(probes) > 12:
            print(f"#   ... (+{len(probes) - 12} kolejnych)")
        print("# DRY-RUN. Dodaj --yes, aby faktycznie nadawać (BENCH!).")
        return 0

    print("# UWAGA: nadawanie na magistralę! Tylko na stole / poza ruchem drogowym.")
    args.silent = False  # nadawanie wymaga trybu normalnego

    log = None
    if not args.no_log:
        os.makedirs(args.log_dir, exist_ok=True)
        fname = "bruteforce_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".log"
        path = os.path.join(args.log_dir, fname)
        log = open(path, "w", encoding="utf-8", buffering=1)
        print(f"# log: {path}")

    bus = open_bus(args)
    results = []
    try:
        for label, aid, data in probes:
            msg = can.Message(arbitration_id=aid, is_extended_id=args.extended, data=data)
            if log:
                log.write(f"# PROBE {label}\n")
            for _ in range(max(1, args.repeats)):
                bus.send(msg)
                if log:
                    log.write(format_frame(msg, "tx") + "\n")
                time.sleep(args.interval)

            reactions: dict = {}
            t_end = time.monotonic() + args.window_ms / 1000.0
            while time.monotonic() < t_end:
                r = bus.recv(timeout=0.005)
                if r is None:
                    continue
                reactions[r.arbitration_id] = reactions.get(r.arbitration_id, 0) + 1
                if log:
                    log.write(format_frame(r, "rx") + "\n")

            if reactions:
                desc = ", ".join(f"0x{a:03X} x{c}" for a, c in
                                 sorted(reactions.items(), key=lambda t: -t[1]))
                print(f"# {label}: ODPOWIEDŹ -> {desc}")
                results.append((label, reactions))
    except KeyboardInterrupt:
        print("\n# przerwano (Ctrl+C)")
    finally:
        bus.shutdown()
        if log:
            log.close()

    print(f"# prób: {len(probes)}, z reakcją: {len(results)}")
    for label, reactions in results[:20]:
        desc = ", ".join(f"0x{a:03X} x{c}" for a, c in
                         sorted(reactions.items(), key=lambda t: -t[1]))
        print(f"#   {label} -> {desc}")
    return 0
