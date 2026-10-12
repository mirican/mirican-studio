"""Narzędzie: profile — przeglądanie profili pojazdów."""

from __future__ import annotations

import argparse
import json

from ..config import PROFILES_DIR, list_profiles, load_profile

NAME = "profile"
HELP = "Profile pojazdów: lista / szczegóły (profiles/*.json)"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name", nargs="?", help="nazwa profilu (np. bmw); bez nazwy = lista")
    parser.add_argument("--dir", action="store_true", help="pokaż katalog profili")


def run(args) -> int:
    if args.dir:
        print(PROFILES_DIR)
        return 0
    if not args.name:
        names = list_profiles()
        print(f"# profile ({PROFILES_DIR}):")
        if not names:
            print("  (brak - utwórz profiles/<nazwa>.json)")
        for name in names:
            try:
                data = load_profile(name)
                print(f"  {name:12s} {data.get('description', '')}")
            except SystemExit:
                print(f"  {name:12s} (błąd odczytu)")
        return 0
    data = load_profile(args.name)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0
