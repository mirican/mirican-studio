"""Punkt wejścia CLI.

``py -m canstudio <narzędzie> [opcje]`` (także przez wrappery ``py sniff.py`` itd.).
Narzędzia są automatycznie pobierane z rejestru ``canstudio.tools.TOOLS``.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__, tools
from .config import resolve_args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="canstudio",
        description="miriCAN Studio — narzędzia do pracy z magistralą CAN "
                    "(nasłuch, wysyłka, analiza, automat, MITM — pełna lista poniżej)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<narzędzie>")
    for module in tools.TOOLS:
        sp = sub.add_parser(module.NAME, help=module.HELP, description=module.HELP)
        module.add_arguments(sp)
        sp.set_defaults(_func=module.run)
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 1
    resolve_args(args)
    return args._func(args) or 0
