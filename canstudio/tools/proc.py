"""Narzędzie: proc — procedury: log -> sesja UDS -> mini-program (procedures/*.json).

Przykłady:
  py -m canstudio proc extract logs\\proc_20261007.log --pair 6F1:6F9 --name "Olej F30" --save
  py -m canstudio proc list
  py -m canstudio proc show olej_f30
"""

from __future__ import annotations

import argparse

from ..config import resolve_path
from ..isotp_log import find_sessions, payloads_per_id, slice_by_window
from ..json_cli import add_json_args, emit, json_mode
from ..logio import read_log
from ..procedures import (compile_procedure, delete_procedure, list_procedures,
                          load_procedure, save_procedure)

NAME = "proc"
HELP = "Procedury: ekstrakcja sesji UDS z nagrania -> mini-program do procedures/"


def cmd_list(args) -> int:
    json_mode(args)
    items = list_procedures()
    if getattr(args, "json", False):
        emit({"ok": True, "procedures": items})
        return 0
    if not items:
        print("# Brak procedur. Nagraj sesję (sniff) i użyj: proc extract <log> --save")
        return 0
    print(f"# procedury ({len(items)}):")
    for it in items:
        sec = " (!) seed/key" if it["security"] else ""
        print(f"  {it['id']:32s} {it['steps']:3d} kroków  "
              f"{it['vehicle'] or '—'}{sec}")
    return 0


def cmd_extract(args) -> int:
    json_mode(args)
    messages = read_log(resolve_path(args.log))
    if not messages:
        print("# Pusty log.")
        return 1
    if args.window:
        a, _, b = args.window.partition(":")
        messages = slice_by_window(messages, float(a), float(b) if b else None)
    only = None
    offset = args.offset
    if args.pair:
        a, _, b = args.pair.partition(":")
        req = int(a, 16)
        only = {req}
        if b:
            offset = int(b, 16) - req
    events, ext = payloads_per_id(messages)
    sessions = find_sessions(events, ext, offset=offset, only_req_ids=only,
                             min_exchanges=(1 if args.pair else args.min_exchanges))
    if not sessions:
        msg = ("Nie znaleziono sesji ISO-TP (para tester<->ECU) — podaj --pair 6F1:6F9 "
               "albo spróbuj --min-exchanges 1")
        if getattr(args, "json", False):
            emit({"ok": False, "error": msg})
        else:
            print(f"# {msg}")
        return 1
    sess = sessions[0]
    name = args.name or f"proc_{sess.req_id:03X}"
    proc = compile_procedure(sess, name=name, vehicle=args.vehicle,
                             source_log=str(args.log))
    print(f"# sesja: 0x{sess.req_id:X} -> 0x{sess.resp_id:X} "
          f"({len(sess.exchanges)} wymian, kroków po kompilacji: {len(proc['steps'])})")
    for i, st in enumerate(proc["steps"], 1):
        exp = st["expect"] or "(brak odpowiedzi w nagraniu)"
        pend = "  [pending]" if st.get("pendings") else ""
        print(f"  {i:2d}. >> {st['send']:<26} << {exp}{pend}")
    if proc["security"]["detected"]:
        print("# UWAGA: wykryto SecurityAccess (seed/key) — same kroki nie wystarczą standalone.")
    saved = None
    if args.save:
        path = save_procedure(proc)
        saved = str(path)
        print(f"# zapisano: {path}")
    if getattr(args, "json", False):
        emit({"ok": True,
              "session": {"txid": sess.req_id, "rxid": sess.resp_id,
                          "exchanges": len(sess.exchanges)},
              "procedure": proc, "saved": saved})
    return 0


def cmd_show(args) -> int:
    json_mode(args)
    try:
        proc = load_procedure(args.name)
    except FileNotFoundError as exc:
        if getattr(args, "json", False):
            emit({"ok": False, "error": str(exc)})
        else:
            print(f"# {exc}")
        return 1
    if getattr(args, "json", False):
        emit({"ok": True, "procedure": proc})
        return 0
    print(f"# {proc['name']} [{proc['id']}]  ({proc.get('vehicle') or '—'})")
    print(f"# format: {proc.get('format')}  kroków: {len(proc.get('steps', []))}"
          + ("  (!) seed/key" if proc.get("security", {}).get("detected") else ""))
    for i, st in enumerate(proc.get("steps", []), 1):
        exp = st.get("expect") or "(brak)"
        print(f"  {i:2d}. >> {st['send']:<26} << {exp}")
    return 0


def cmd_rm(args) -> int:
    json_mode(args)
    if not args.yes:
        raise SystemExit("Usunięcie procedury wymaga --yes")
    try:
        path = delete_procedure(args.name)
    except FileNotFoundError as exc:
        if getattr(args, "json", False):
            emit({"ok": False, "error": str(exc)})
        else:
            print(f"# {exc}")
        return 1
    if getattr(args, "json", False):
        emit({"ok": True, "removed": str(path)})
    else:
        print(f"# usunięto: {path}")
    return 0


def add_arguments(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="tryb", metavar="<tryb>")

    p = sub.add_parser("list", help="lista zapisanych procedur")
    add_json_args(p)
    p.set_defaults(_cmd=cmd_list)

    p = sub.add_parser("extract", help="ekstrakcja procedury z nagrania")
    p.add_argument("log", help="plik logu (candump/.asc/.blf)")
    p.add_argument("--pair", help="kanał tester<->ECU w hex, np. 6F1:6F9 (domyślnie: auto +offset)")
    p.add_argument("--offset", type=int, default=8, help="offset odpowiedzi (domyślnie 8)")
    p.add_argument("--window", help="okno nagrania [s] od początku logu, np. '12:48'")
    p.add_argument("--name", help="nazwa procedury (do zapisu)")
    p.add_argument("--vehicle", default="", help="opis pojazdu")
    p.add_argument("--min-exchanges", type=int, default=2, help="min. wymian dla sesji")
    p.add_argument("--save", action="store_true", help="zapisz do procedures/<id>.json")
    add_json_args(p)
    p.set_defaults(_cmd=cmd_extract)

    p = sub.add_parser("show", help="pokaż procedurę")
    p.add_argument("name", help="id/nazwa procedury")
    add_json_args(p)
    p.set_defaults(_cmd=cmd_show)

    p = sub.add_parser("rm", help="usuń procedurę")
    p.add_argument("name")
    p.add_argument("--yes", action="store_true", help="potwierdź usunięcie")
    add_json_args(p)
    p.set_defaults(_cmd=cmd_rm)


def run(args) -> int:
    fn = getattr(args, "_cmd", None)
    if fn is None:
        print("Użyj: py -m canstudio proc {list|extract|show|rm} …")
        return 1
    return fn(args)
