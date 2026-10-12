"""Narzędzie: gui — miriCAN Studio w przeglądarce (lokalny serwer)."""

from __future__ import annotations

import argparse

NAME = "gui"
HELP = "miriCAN Studio GUI — interfejs graficzny w przeglądarce (live trace, TX, REC)"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="127.0.0.1", help="adres serwera (domyślnie 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8077, help="port serwera (domyślnie 8077)")
    parser.add_argument("--no-browser", action="store_true", help="nie otwieraj przeglądarki")
    parser.add_argument("--idle-exit", type=int, default=None,
                        help="sekundy bez otwartego GUI, po których serwer sam się zamknie "
                             "(zwalnia port COM); 0 = nigdy. Domyślnie 30, a 0 przy --no-browser")


def run(args) -> int:
    import importlib.util

    missing = [m for m in ("fastapi", "uvicorn", "websockets")
               if importlib.util.find_spec(m) is None]
    if missing:
        print("# Brak zależności GUI. Zainstaluj:")
        print("#   py -m pip install fastapi uvicorn websockets")
        return 1
    from ..gui.server import run as run_gui
    idle = args.idle_exit if args.idle_exit is not None else (0 if args.no_browser else 30)
    run_gui(host=args.host, port=args.port, open_browser=not args.no_browser, idle_exit=idle)
    return 0
