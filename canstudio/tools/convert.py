"""Narzędzie: convert — konwersja logów (candump <-> .asc; odczyt .blf)."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..config import resolve_path
from ..logio import read_log, write_asc, write_candump

NAME = "convert"
HELP = "Konwersja logów: candump <-> .asc (odczyt .blf)"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", help="plik wejściowy (.log/.txt candump, .asc, .blf)")
    parser.add_argument("output", help="plik wyjściowy (.log = candump, .asc = Vector ASCII)")


def run(args) -> int:
    messages = read_log(resolve_path(args.input))
    out = Path(resolve_path(args.output))
    ext = out.suffix.lower()
    if ext == ".asc":
        n = write_asc(out, messages)
    elif ext in (".log", ".txt", ""):
        n = write_candump(out, messages)
    elif ext == ".blf":
        print("# Zapis .blf nie jest obsługiwany (python-can nie umie zapisywać BLF).")
        print("# Wybierz format wyjściowy .log albo .asc.")
        return 1
    else:
        print(f"# Nieznane rozszerzenie wyjścia: {ext!r}")
        return 1
    print(f"# {len(messages)} ramek: {args.input} -> {args.output} ({n} zapisanych)")
    return 0
