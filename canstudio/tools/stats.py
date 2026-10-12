"""Narzędzie: stats — tabela per ID z logu (okresy, częstotliwości, dane)."""

from __future__ import annotations

import argparse

from ..config import resolve_path
from ..frames import parse_ids
from ..json_cli import add_json_args, emit, json_mode
from ..logio import read_log
from ..stats import estimate_period

NAME = "stats"
HELP = "Tabela per ID z logu: liczba ramek, okres (~ms), częstotliwość, ostatnie dane"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("log", help="plik logu (candump/.asc/.blf)")
    parser.add_argument("--top", type=int, default=40, help="ile ID pokazać")
    parser.add_argument("--min-count", type=int, default=1, help="min. liczba ramek")
    parser.add_argument("--ids", help="tylko te ID (np. 0x130,0x1A0)")
    parser.add_argument("--sort", choices=("count", "id"), default="count", help="sortowanie")
    add_json_args(parser)


def run(args) -> int:
    json_mode(args)
    messages = read_log(resolve_path(args.log))
    if not messages:
        print("# Brak ramek w logu.")
        return 1

    rows: dict = {}
    for m in messages:
        d = rows.setdefault(m.arbitration_id, {"count": 0, "times": [], "last": b""})
        d["count"] += 1
        d["times"].append(m.timestamp)
        d["last"] = bytes(m.data)

    want = parse_ids(args.ids) if args.ids else None
    items = [(aid, d) for aid, d in rows.items()
             if (want is None or aid in want) and d["count"] >= args.min_count]
    if args.sort == "count":
        items.sort(key=lambda t: t[1]["count"], reverse=True)
    else:
        items.sort(key=lambda t: t[0])
    items = items[:args.top]

    jrows = []
    for aid, d in items:
        per = estimate_period(d["times"])
        jrows.append({"id": aid, "count": d["count"], "period": per,
                      "last": d["last"].hex().upper()})
    if getattr(args, "json", False):
        emit({"ok": True, "file": str(args.log), "frames": len(messages),
              "unique_ids": len(rows), "ids": jrows})
        return 0

    print(f"# {args.log}: {len(messages)} ramek, {len(rows)} unikalnych ID")
    print(f"#  {'ID':>8}  {'ramek':>7}  {'okres':>8}  {'czest.':>9}  DANE (ostatnie)")
    for aid, d in items:
        per = estimate_period(d["times"])
        per_s = f"{per * 1000:.1f} ms" if per else "-"
        freq = f"{1 / per:.1f} Hz" if per and per > 0 else "-"
        print(f"   0x{aid:03X}  {d['count']:>7}  {per_s:>8}  {freq:>9}  {d['last'].hex(' ').upper()}")
    return 0
