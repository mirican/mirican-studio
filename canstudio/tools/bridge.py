"""Narzędzie: bridge — man in the middle między dwoma interfejsami CAN."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import threading
import time

from ..bridging import (BridgeLogger, BridgeRules, demo_virtual, make_endpoint_args,
                        parse_checksum_spec, parse_counter_spec, parse_endpoint,
                        parse_set_spec, run_bridge)
from ..bus import open_bus
from ..config import resolve_path
from ..frames import parse_id

NAME = "bridge"
HELP = "MITM: przekazywanie/modyfikacja ramek między dwoma kanałami CAN (2 interfejsy)"


# parse_endpoint / make_endpoint_args / parse_*_spec pochodzą z canstudio.bridging (wspólne z GUI i replay)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--in", dest="endpoint_in",
                        help="wejście, np. slcan:COM7 lub virtual:vA")
    parser.add_argument("--out", dest="endpoint_out",
                        help="wyjście, np. slcan:COM8 lub virtual:vB")
    parser.add_argument("--bitrate", "-b", type=int, default=500000, help="prędkość magistrali")
    parser.add_argument("--tty-baud", type=int, default=115200, help="prędkość portu COM")
    parser.add_argument("--rules", help="plik JSON z regułami (drop/set/counter/checksum)")
    parser.add_argument("--set", action="append", default=[], metavar="ID:BYTE=VALUE",
                        help="ustaw bajt w ramce (można wielokrotnie)")
    parser.add_argument("--counter", action="append", default=[], metavar="ID:BYTE",
                        help="prowadź licznik (auto +1 na każdej przekazanej ramce)")
    parser.add_argument("--checksum", action="append", default=[], metavar="ID:BYTE:ALGO",
                        help="automatycznie przeliczaj sumę (np. 0x130:7:xor8)")
    parser.add_argument("--drop", help="pomiń ID (np. 0x2C0,0x2C1)")
    parser.add_argument("--tap", action="store_true",
                        help="tryb nasłuchu: tylko loguj, NIE przekazuj")
    parser.add_argument("--duration", type=float, default=0.0, help="czas pracy w s [0 = bez limitu]")
    parser.add_argument("--log-dir", default=None, help="katalog na logi (domyślnie logs/)")
    parser.add_argument("--no-log", action="store_true", help="nie zapisuj logu")
    parser.add_argument("--demo", action="store_true",
                        help="demo MITM na magistralach wirtualnych (bez sprzętu)")


def run(args) -> int:
    if args.demo:
        return 0 if demo_virtual(verbose=True) else 1

    if not args.endpoint_in or not args.endpoint_out:
        print("# Podaj --in i --out, np.:")
        print("#   py -m canstudio bridge --in slcan:COM7 --out slcan:COM8")
        print("# Demo bez sprzętu: py -m canstudio bridge --demo")
        return 1

    rules = BridgeRules()
    if args.rules:
        with open(resolve_path(args.rules), "r", encoding="utf-8") as fh:
            rules = BridgeRules.from_mapping(json.load(fh))
    rules.set_rules += [parse_set_spec(s) for s in args.set]
    rules.counter_rules += [parse_counter_spec(s) for s in args.counter]
    rules.checksum_rules += [parse_checksum_spec(s) for s in args.checksum]
    if args.drop:
        rules.drop_ids |= {parse_id(x) for x in args.drop.replace(";", ",").split(",") if x.strip()}
    rules.tap = args.tap

    iface_in, channel_in = parse_endpoint(args.endpoint_in)
    iface_out, channel_out = parse_endpoint(args.endpoint_out)
    ep_in = make_endpoint_args(iface_in, channel_in, args.bitrate, args.tty_baud)
    ep_out = make_endpoint_args(iface_out, channel_out, args.bitrate, args.tty_baud)
    try:
        bus_in = open_bus(ep_in)
        bus_out = open_bus(ep_out)
    except Exception as exc:  # noqa: BLE001
        print(f"# Błąd otwarcia magistral: {exc}")
        return 1

    logger = None
    if not args.no_log:
        os.makedirs(args.log_dir, exist_ok=True)
        fname = "bridge_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".log"
        path = os.path.join(args.log_dir, fname)
        logger = BridgeLogger(path)
        print(f"# log: {path}")

    mode = "TAP (tylko podgląd)" if rules.tap else "MITM (przekazywanie A<->B)"
    print(f"# {mode}: {args.endpoint_in} <-> {args.endpoint_out} @ {args.bitrate} bit/s")
    if not rules.tap:
        print("# UWAGA: ramki są przekazywane na żywo - upewnij się, że to bezpieczne")
    n_rules = len(rules.set_rules) + len(rules.counter_rules) + len(rules.checksum_rules)
    print(f"# reguły: drop={len(rules.drop_ids)}, modyfikacje={n_rules}")

    stop = threading.Event()
    stats: dict = {}
    threads = [
        threading.Thread(target=run_bridge,
                         args=(bus_in, bus_out, rules, "A>B", logger, stop, 0.05, stats),
                         daemon=True),
        threading.Thread(target=run_bridge,
                         args=(bus_out, bus_in, rules, "B>A", logger, stop, 0.05, stats),
                         daemon=True),
    ]
    for thread in threads:
        thread.start()

    t_start = time.monotonic()
    try:
        while True:
            time.sleep(2.0)
            print(f"# przekazano={stats.get('fwd', 0)} zmodyfikowano={stats.get('mod', 0)} "
                  f"pominięto={stats.get('dropped', 0)} błędów={stats.get('errors', 0)}")
            if args.duration and (time.monotonic() - t_start) >= args.duration:
                break
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=1.0)
        bus_in.shutdown()
        bus_out.shutdown()
        if logger:
            logger.close()
    print(f"# koniec: przekazano={stats.get('fwd', 0)} zmodyfikowano={stats.get('mod', 0)}")
    return 0
