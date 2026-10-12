"""Narzędzie: diff — porównanie dwóch logów CAN."""

from __future__ import annotations

import argparse

from ..config import resolve_path
from ..diffing import diff_logs
from ..frames import parse_ids
from ..logio import read_log

NAME = "diff"
HELP = "Porównanie dwóch logów (co się zmieniło między nagraniami / trybami)"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("log_a", help="pierwszy log (bazowy)")
    parser.add_argument("log_b", help="drugi log (np. po wciśnięciu przycisku)")
    parser.add_argument("--top", type=int, default=8, help="ile ID pokazać")
    parser.add_argument("--bytes", type=int, default=6, help="ile bajtów na ID")
    parser.add_argument("--min-frames", type=int, default=10, help="min. liczba ramek do porównania")
    parser.add_argument("--ids", help="filtruj ID (np. 0x130,0x1A0)")


def run(args) -> int:
    a = read_log(resolve_path(args.log_a))
    b = read_log(resolve_path(args.log_b))
    print(f"# A: {args.log_a} ({len(a)} ramek)")
    print(f"# B: {args.log_b} ({len(b)} ramek)")

    if args.ids:
        want = parse_ids(args.ids)
        a = [m for m in a if m.arbitration_id in want]
        b = [m for m in b if m.arbitration_id in want]

    diffs, only = diff_logs(a, b, min_frames=args.min_frames,
                            per_id_bytes=args.bytes, top_ids=args.top)

    print()
    print("== ID ze zmianami (posortowane po sile zmian) ==")
    if not diffs:
        print("  (brak wspólnych ID ze zmianami)")
    for d in diffs:
        print(f"ID 0x{d.arbitration_id:03X}: {d.n_a} vs {d.n_b} ramek (score {d.score:.0f})")
        for bd in d.bytes:
            note = f"  [{bd.note}]" if bd.note else ""
            print(f"    bajt {bd.byte}: średnia {bd.mean_a:.1f} -> {bd.mean_b:.1f}"
                  f" | A{bd.values_a} B{bd.values_b}{note}")

    if only["A"]:
        print()
        print("== tylko w A ==")
        for aid, cnt in only["A"][:15]:
            print(f"  0x{aid:03X} x{cnt}")
    if only["B"]:
        print()
        print("== tylko w B ==")
        for aid, cnt in only["B"][:15]:
            print(f"  0x{aid:03X} x{cnt}")
    return 0
