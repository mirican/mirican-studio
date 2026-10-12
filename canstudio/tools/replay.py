"""Narzędzie: replay — odtwarzanie logu candump na magistralę."""

from __future__ import annotations

import argparse
import time

import can

from ..bridging import (BridgeState, BridgeRules, parse_checksum_spec,
                        parse_counter_spec, parse_set_spec, transform)
from ..bus import add_bus_args, open_bus
from ..config import resolve_path
from ..frames import frame_from_message, parse_frame_line, parse_ids
from ..json_cli import add_json_args, emit, json_mode
from ..logio import read_log

NAME = "replay"
HELP = "Odtwarzanie logu CAN na magistralę (z regulacją tempa)"


def load_frames(path: str):
    """Lista ramek (Frame) z pliku candump; dla .asc/.blf konwertuje w locie."""
    from pathlib import Path

    ext = Path(path).suffix.lower()
    if ext in (".asc", ".blf"):
        return [frame_from_message(m, str(getattr(m, "channel", "") or "can0"))
                for m in read_log(path)]

    frames = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                frames.append(parse_frame_line(line))
            except ValueError:
                continue
    return frames


def add_arguments(parser: argparse.ArgumentParser) -> None:
    add_bus_args(parser)
    parser.add_argument("--profile", help="profil pojazdu (ustawia m.in. bitrate)")
    parser.add_argument("file", help="plik logu (format candump / candump -L)")
    parser.add_argument("--rate", type=float, default=1.0,
                        help="mnożnik tempa (2 = dwa razy szybciej, 0.5 = wolniej)")
    parser.add_argument("--max-gap", type=float, default=5.0,
                        help="maksymalna odtwarzana przerwa między ramkami [s]")
    parser.add_argument("--skip-ids", help="pomiń ID, np. 0x7E8,0x7E9")
    parser.add_argument("--loop", action="store_true", help="zapętlaj odtwarzanie")
    parser.add_argument("--limit", type=int, default=0, help="limit ramek (0 = bez limitu)")
    parser.add_argument("--set", action="append", default=[], metavar="ID:BYTE=VALUE",
                        help="modyfikacja: ustaw bajt (można wielokrotnie)")
    parser.add_argument("--counter", action="append", default=[], metavar="ID:BYTE",
                        help="modyfikacja: napraw licznik (auto +1)")
    parser.add_argument("--checksum", action="append", default=[], metavar="ID:BYTE:ALGO",
                        help="modyfikacja: przelicz sumę (np. 0x130:7:xor8)")
    parser.add_argument("--drop", help="modyfikacja: pomiń ID przy wysyłce (np. 0x2C0)")
    add_json_args(parser)


def run(args) -> int:
    json_mode(args)
    frames = load_frames(resolve_path(args.file))
    if not frames:
        raise SystemExit("Brak ramek do odtworzenia.")

    if args.skip_ids:
        skip = parse_ids(args.skip_ids)
        frames = [f for f in frames if f.arbitration_id not in skip]
    if not frames:
        raise SystemExit("Po filtrach nie zostało nic do odtworzenia.")

    rules = BridgeRules()
    rules.set_rules += [parse_set_spec(s) for s in args.set]
    rules.counter_rules += [parse_counter_spec(s) for s in args.counter]
    rules.checksum_rules += [parse_checksum_spec(s) for s in args.checksum]
    if args.drop:
        rules.drop_ids |= parse_ids(args.drop)
    mods = (len(rules.set_rules) + len(rules.counter_rules)
            + len(rules.checksum_rules) + len(rules.drop_ids))

    rate = args.rate if args.rate > 0 else 1.0
    print(f"# {len(frames)} ramek z {args.file} (rate={rate})"
          + (f", modyfikacje: {mods}" if mods else ""))
    print("# UWAGA: odtwarzanie wysyła ramki na magistralę - bądź ostrożny")

    bus = open_bus(args)
    sent = 0
    modified = 0
    state = BridgeState()
    try:
        while True:
            prev_ts = frames[0].timestamp
            schedule = 0.0
            t0 = time.monotonic()
            for frame in frames:
                delta = max(0.0, min(frame.timestamp - prev_ts, args.max_gap))
                prev_ts = frame.timestamp
                schedule += delta / rate
                now = time.monotonic() - t0
                if schedule > now:
                    time.sleep(schedule - now)
                if frame.arbitration_id in rules.drop_ids:
                    continue
                data, was_mod = transform(frame.data, frame.arbitration_id, rules,
                                          state, "replay")
                if was_mod:
                    modified += 1
                bus.send(can.Message(arbitration_id=frame.arbitration_id,
                                     is_extended_id=frame.is_extended, data=data))
                sent += 1
                if args.limit and sent >= args.limit:
                    raise KeyboardInterrupt
            if not args.loop:
                break
    except KeyboardInterrupt:
        pass
    finally:
        bus.shutdown()
    print(f"# odtworzono {sent} ramek"
          + (f" (zmodyfikowano {modified})" if modified else ""))
    if getattr(args, "json", False):
        emit({"ok": True, "sent": sent, "modified": modified, "file": str(args.file)})
    return 0
