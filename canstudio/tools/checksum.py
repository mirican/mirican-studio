"""Narzędzie: checksum — detekcja liczników i sum kontrolnych."""

from __future__ import annotations

import argparse
from dataclasses import asdict

from ..checksums import analyze_frames
from ..config import resolve_path
from ..frames import parse_ids
from ..json_cli import add_json_args, emit, json_mode
from ..logio import read_log
from ..stats import group_bytes_by_id

NAME = "checksum"
HELP = "Detekcja liczników i sum kontrolnych w ramkach (na bazie logu)"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("log", help="plik logu (candump/.asc/.blf)")
    parser.add_argument("--id", dest="ids", help="analizuj tylko te ID (np. 0x130,0x1A0)")
    parser.add_argument("--top", type=int, default=5,
                        help="ile najczęstszych ID przeanalizować (gdy brak --id)")
    parser.add_argument("--min-frames", type=int, default=20,
                        help="min. liczba ramek do wiarygodnej analizy")
    add_json_args(parser)


def run(args) -> int:
    json_mode(args)
    messages = read_log(resolve_path(args.log))
    groups = group_bytes_by_id(messages)
    if not groups:
        print("# Brak ramek w logu.")
        return 1

    if args.ids:
        targets = [aid for aid in sorted(parse_ids(args.ids)) if aid in groups]
    else:
        targets = [aid for aid, _ in
                   sorted(((aid, len(v)) for aid, v in groups.items()),
                          key=lambda t: t[1], reverse=True)[:args.top]]

    print(f"# analiza {len(targets)} ID z {args.log} ({len(messages)} ramek)")
    jids = []
    for aid in targets:
        result = analyze_frames(groups[aid])
        jids.append({"id": aid, "dlc": result.dlc, "count": result.count,
                     "counters": [asdict(c) for c in result.counters],
                     "checksums": [asdict(h) for h in result.checksums],
                     "weak": [asdict(h) for h in result.weak_checksums]})
        print()
        print(f"ID 0x{aid:03X}  (dlc={result.dlc}, ramek={result.count})")
        if result.count < args.min_frames:
            print(f"  (za mało ramek - potrzeba >= {args.min_frames})")
            continue
        if result.counters:
            for c in result.counters:
                print(f"  LICZNIK: bajt {c.byte} — {c.kind} ({c.score * 100:.1f}% kolejnych par)")
        if result.checksums:
            for h in result.checksums:
                if h.byte < 0:
                    print(f"  SUMA:    {h.algo} ({h.score * 100:.1f}%)")
                else:
                    print(f"  SUMA:    bajt {h.byte} — {h.algo} ({h.score * 100:.1f}% zgodności)")
        if result.weak_checksums and not result.checksums:
            for h in result.weak_checksums[:4]:
                if h.byte < 0:
                    print(f"  słabe dopasowanie: {h.algo} ({h.score * 100:.1f}%)")
                else:
                    print(f"  słabe dopasowanie: bajt {h.byte} — {h.algo} ({h.score * 100:.1f}%)")
        if not result.counters and not result.checksums:
            print("  (nie wykryto licznika ani sumy kontrolnej)")
    if getattr(args, "json", False):
        emit({"ok": True, "file": str(args.log), "ids": jids})
    return 0
