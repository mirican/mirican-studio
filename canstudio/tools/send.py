"""Narzędzie: send — wysyłanie ramek CAN (pojedynczo / cyklicznie / przemiatanie).

Obsługuje „smooth change" (--sweep), automatyczne prowadzenie licznika
(--counter) i przeliczanie sumy kontrolnej (--checksum) — jak w analizatorach
pokroju CAN SHARK, ale z linii poleceń.
"""

from __future__ import annotations

import argparse
import time

import can

from ..bridging import (BridgeRules, BridgeState, ChecksumRule, CounterRule,
                        transform)
from ..bus import add_bus_args, open_bus
from ..frames import parse_id
from ..json_cli import add_json_args, emit, json_mode

NAME = "send"
HELP = "Wysyłanie ramek CAN (pojedynczo / cyklicznie / sweep + auto-licznik/suma)"


def parse_data(text: str) -> bytes:
    cleaned = text.replace(" ", "").replace(",", "").replace("0x", "").replace(":", "")
    if len(cleaned) % 2:
        raise SystemExit("Dane muszą mieć parzystą liczbę znaków hex (np. 'DE AD BE EF')")
    if len(cleaned) > 16:
        raise SystemExit("Klasyczny CAN: max 8 bajtów (16 znaków hex)")
    return bytes.fromhex(cleaned)


def parse_sweep(spec: str):
    """'BYTE:START-END[:STEP]', np. '3:0-255' albo '3:00-FF:2'."""
    parts = spec.split(":")
    if len(parts) < 2:
        raise SystemExit("Format sweep: BYTE:START-END[:STEP], np. '3:0-255'")
    byte = int(parts[0], 0)
    start_raw, _, end_raw = parts[1].partition("-")
    if not end_raw:
        raise SystemExit("Format sweep: BYTE:START-END[:STEP], np. '3:0-255'")
    start, end = parse_id(start_raw), parse_id(end_raw)
    if start > end:
        start, end = end, start
    step = int(parts[2], 0) if len(parts) > 2 else 1
    return byte, start, end, max(1, step)


def parse_checksum_opt(spec: str):
    """'BYTE:ALGO', np. '7:xor8'."""
    byte_raw, _, algo = spec.partition(":")
    return int(byte_raw, 0), algo


def add_arguments(parser: argparse.ArgumentParser) -> None:
    add_bus_args(parser)
    parser.add_argument("--profile", help="profil pojazdu (ustawia m.in. bitrate)")
    parser.add_argument("--id", required=True, type=parse_id, help="ID ramki, np. 0x123 (hex/dec)")
    parser.add_argument("--data", default="", help="dane hex, np. 'DE AD BE EF' (puste = 0 bajtów)")
    parser.add_argument("--extended", action="store_true", help="ramka o rozszerzonym ID (29 bit)")
    parser.add_argument("--count", type=int, default=1, help="liczba powtórzeń (0 = bez limitu)")
    parser.add_argument("--interval", type=float, default=0.1, help="odstęp między ramkami [s]")
    parser.add_argument("--sweep", metavar="BYTE:START-END[:STEP]",
                        help="płynna zmiana bajtu, np. '3:0-255' (smooth change)")
    parser.add_argument("--counter", type=int, metavar="BYTE",
                        help="auto-licznik: wskazany bajt rośnie o 1 przy każdej ramce")
    parser.add_argument("--checksum", metavar="BYTE:ALGO",
                        help="auto-suma kontrolna, np. '7:xor8' (algorytmy jak w `checksum`)")
    parser.add_argument("--dry-run", action="store_true", help="pokaż plan wysyłki i wyjdź")
    add_json_args(parser)


def run(args) -> int:
    json_mode(args)
    data = parse_data(args.data) if args.data else b""
    sweep = parse_sweep(args.sweep) if args.sweep else None
    if sweep and len(data) <= sweep[0]:
        raise SystemExit(f"Sweep wskazuje bajt {sweep[0]}, ale dane mają tylko {len(data)} bajtów")

    rules = None
    state = None
    if args.counter is not None or args.checksum:
        rules = BridgeRules()
        if args.counter is not None:
            rules.counter_rules.append(CounterRule(args.id, args.counter))
        if args.checksum:
            byte, algo = parse_checksum_opt(args.checksum)
            rules.checksum_rules.append(ChecksumRule(args.id, byte, algo))
        state = BridgeState()

    if args.dry_run:
        plan = f"# dry-run: ID=0x{args.id:X}, dane={data.hex(' ').upper() or '-'}"
        if sweep:
            plan += f", sweep b{sweep[0]} {sweep[1]}..{sweep[2]} step {sweep[3]}"
        if args.counter is not None:
            plan += f", counter b{args.counter}"
        if args.checksum:
            plan += f", checksum {args.checksum}"
        print(plan)
        if getattr(args, "json", False):
            emit({"ok": True, "dry_run": True, "id": args.id,
                  "data": data.hex(" ").upper()})
        return 0

    bus = open_bus(args)
    sent = 0
    sweep_value = sweep[1] if sweep else None
    if args.count == 0:
        print("# UWAGA: wysyłka ciągła (Ctrl+C przerywa)")
    try:
        while True:
            payload = bytearray(data)
            if sweep:
                payload[sweep[0]] = sweep_value
                sweep_value += sweep[3]
                if sweep_value > sweep[2]:
                    sweep_value = sweep[1]
            if rules:
                payload = bytearray(transform(bytes(payload), args.id, rules, state, "send")[0])
            msg = can.Message(
                arbitration_id=args.id,
                is_extended_id=args.extended,
                data=bytes(payload),
                is_fd=args.fd,
            )
            bus.send(msg)
            sent += 1
            print(f"# TX {sent}: ID=0x{args.id:X}{' (ext)' if args.extended else ''} "
                  f"DLC={len(payload)} DATA={bytes(payload).hex(' ').upper() or '-'}")
            if args.count and sent >= args.count:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        bus.shutdown()
    print(f"# wysłano {sent} ramek")
    if getattr(args, "json", False):
        emit({"ok": True, "sent": sent, "id": args.id})
    return 0
