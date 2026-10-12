"""Narzędzie: correlate — korelacja znaczników z ramkami."""

from __future__ import annotations

import argparse

from ..config import resolve_path
from ..json_cli import add_json_args, emit, json_mode
from ..markers import correlate, read_candump_with_markers

NAME = "correlate"
HELP = "Co się zmienia po znacznikach? (np. który bajt reaguje na wciśnięty przycisk)"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("log", help="log candump ze znacznikami (nagraj: sniff --marks)")
    parser.add_argument("--window", type=float, default=1.5, help="okno analizy po znaczniku [s]")
    parser.add_argument("--pre", type=float, default=1.0, help="zapas dla wartości bazowej [s]")
    parser.add_argument("--top", type=int, default=10, help="ile kandydatów pokazać")
    parser.add_argument("--label", help="analizuj tylko tę etykietę")
    add_json_args(parser)


def run(args) -> int:
    json_mode(args)
    messages, markers = read_candump_with_markers(resolve_path(args.log))
    if not markers:
        print("# Brak znaczników w logu.")
        print("# Nagraj z: py -m canstudio sniff --marks --channel COM7")
        print("# (ENTER = znacznik, tekst + ENTER = etykieta, np. 'przycisk szyby')")
        return 1
    if args.label:
        markers = [m for m in markers if m.label == args.label]
        if not markers:
            print(f"# Brak znaczników o etykiecie {args.label!r}")
            return 1

    print(f"# {len(messages)} ramek, {len(markers)} znaczników, okno {args.window}s")
    report = correlate(messages, markers, window_s=args.window, pre_s=args.pre, top=args.top)
    jlabels = {}
    for label, (count, cands) in report.items():
        jlabels[label] = {"count": count, "candidates": [
            {"id": c.arbitration_id, "byte": c.byte, "hits": c.hits,
             "total": c.total, "baseline": round(c.baseline, 4)} for c in cands]}
    if getattr(args, "json", False):
        emit({"ok": True, "file": str(args.log), "labels": jlabels})
        return 0
    for label, (count, cands) in report.items():
        print(f"\n# Etykieta: {label!r}  (powtórzeń: {count})")
        if count < 2:
            print("#   (uwaga: dla pewności powtórz akcję kilka razy)")
        if not cands:
            print("   (brak kandydatów)")
        for c in cands:
            pct = 100.0 * c.hits / c.total
            print(f"   0x{c.arbitration_id:03X} bajt {c.byte}: trafienia {c.hits}/{c.total} "
                  f"({pct:.0f}%), tło ~{c.baseline * 100:.0f}%")
    return 0
