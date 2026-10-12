"""Narzędzie: discover — automatyczna klasyfikacja bajtów w logu."""

from __future__ import annotations

import argparse

from ..config import resolve_path
from ..detect import classify_frames
from ..frames import parse_ids
from ..json_cli import add_json_args, emit, json_mode
from ..logio import read_log
from ..stats import group_bytes_by_id

NAME = "discover"
HELP = "Klasyfikacja bajtów: liczniki, sumy, przełączniki (przyciski), sensory"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("log", help="plik logu (candump/.asc/.blf)")
    parser.add_argument("--id", dest="ids", help="tylko te ID (np. 0x130,0x2CA)")
    parser.add_argument("--top", type=int, default=6, help="ile najczęstszych ID (gdy brak --id)")
    parser.add_argument("--min-frames", type=int, default=12, help="min. liczba ramek dla ID")
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

    print(f"# discover: {len(targets)} ID z {args.log} ({len(messages)} ramek)")
    candidates = []
    jids = []
    for aid in targets:
        frames = groups[aid]
        if len(frames) < args.min_frames:
            print(f"\nID 0x{aid:03X}: za mało ramek ({len(frames)})")
            continue
        classes = classify_frames(frames)
        jids.append({"id": aid, "frames": len(frames), "dlc": len(frames[0]),
                     "classes": [{"byte": c.byte, "kind": c.kind, "detail": c.detail}
                                 for c in classes]})
        print(f"\nID 0x{aid:03X}  (ramek={len(frames)}, dlc={len(frames[0])}):")
        for c in classes:
            print(f"  b{c.byte}: {c.kind:22s} {c.detail}")
            if c.kind.startswith("przełącznik"):
                candidates.append((aid, c.byte, c.detail))

    if candidates:
        print("\n# KANDYDACI NA PRZYCISKI / FLAGI (bajty o rzadkich zmianach):")
        for aid, byte, detail in candidates:
            print(f"#   0x{aid:03X} b{byte}: {detail}")
    if getattr(args, "json", False):
        emit({"ok": True, "file": str(args.log), "ids": jids})
    return 0
