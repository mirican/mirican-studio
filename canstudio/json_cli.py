"""Wyjście maszynowe dla agentów: ``--json`` / ``--jsonl``.

Wzorzec użycia w narzędziu::

    from ..json_cli import add_json_args, json_mode, emit, emitl

    def add_arguments(parser):
        add_json_args(parser)          # dodaje --json (opcjonalnie --jsonl)

    def run(args):
        json_mode(args)                # w trybie maszynowym: print() -> stderr
        ...
        emit({"ok": True, ...})        # czysty JSON na prawdziwym stdout
        emitl({"t": ..., "id": ...})   # jedna linia JSONL (strumień)

Dzięki temu cały „ludzki” tekst idzie na stderr, a stdout zostaje czysty
dla parsera (np. agenta). ``reset()`` przywraca stan (dla testów).
"""

from __future__ import annotations

import json
import sys

_real_stdout = None


def add_json_args(parser, jsonl: bool = False) -> None:
    """Dodaje --json (i opcjonalnie --jsonl) do parsera narzędzia."""
    g = parser.add_argument_group("wyjście maszynowe (dla agentów)")
    g.add_argument("--json", action="store_true",
                   help="wynik jako JSON na stdout (komunikaty na stderr)")
    if jsonl:
        g.add_argument("--jsonl", action="store_true",
                       help="strumień JSONL na stdout (jedna linia na ramkę/zdarzenie)")


def json_mode(args) -> bool:
    """Włącza tryb maszynowy: wszystkie ``print()`` idą na stderr.

    Zwraca True, gdy włączone. Idempotentne.
    """
    global _real_stdout
    if not (getattr(args, "json", False) or getattr(args, "jsonl", False)):
        return False
    if _real_stdout is None:
        _real_stdout = sys.stdout
        sys.stdout = sys.stderr
    return True


def reset() -> None:
    """Przywraca oryginalny stdout (do testów / kolejnych narzędzi w procesie)."""
    global _real_stdout
    if _real_stdout is not None:
        sys.stdout = _real_stdout
        _real_stdout = None


def _target():
    return _real_stdout or sys.stdout


def emit(obj) -> None:
    """Jeden obiekt JSON na prawdziwym stdout (odporny na kodowanie konsoli)."""
    out = _target()
    try:
        out.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
    except UnicodeEncodeError:
        out.write(json.dumps(obj, ensure_ascii=True, default=str) + "\n")
    try:
        out.flush()
    except Exception:  # noqa: BLE001
        pass


def emitl(obj) -> None:
    """Linia strumienia JSONL (alias emit — jedna linia na wywołanie)."""
    emit(obj)
