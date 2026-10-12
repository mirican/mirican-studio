"""Narzędzie: autodbc — wstępny plik DBC z logu albo z nasłuchu.

Generuje plik ``.dbc`` (cantools/DBC), w którym każdy bajt każdej ramki jest
sygnałem z nazwą wg klasy (counter/checksum/switch/sensor/const...). Umożliwia
dekodowanie surowych logów bez ręcznego pisania DBC — przydatne tuż po sesji
ze świeżym autem.
"""

from __future__ import annotations

import argparse
import time
from collections import Counter as _Count
from pathlib import Path

from .. import __version__
from ..bus import add_bus_args, open_bus
from ..config import ROOT, resolve_path
from ..dbc import load_dbc
from ..dbcgen import build_dbc, kind_label
from ..detect import classify_frames
from ..frames import parse_ids
from ..json_cli import add_json_args, emit, json_mode
from ..logio import read_log
from ..stats import estimate_period

NAME = "autodbc"
HELP = "Auto-DBC: wstępny .dbc z logu / nasłuchu (liczniki, sumy, przyciski, sensory)"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("log", nargs="?", help="plik logu (candump/.asc/.blf); pomiń przy --capture")
    parser.add_argument("--capture", type=float, metavar="SEK",
                        help="zbierz ramki na żywo przez SEK sekund (zamiast logu)")
    add_bus_args(parser)
    parser.add_argument("--profile", help="profil pojazdu (bitrate dla --capture)")
    parser.add_argument("--out", help="ścieżka wyjściowa (domyślnie dbc/auto_<nazwa>.dbc)")
    parser.add_argument("--ids", help="tylko te ID, np. 0x130,0x2CA")
    parser.add_argument("--top", type=int, default=24,
                        help="limit liczby ID (po liczbie ramek; domyślnie 24)")
    parser.add_argument("--min-frames", type=int, default=12,
                        help="min. ramek wymaganych dla ID (domyślnie 12)")
    add_json_args(parser)


def _collect_live(args) -> list:
    print(f"# nasłuch {args.capture:.0f} s ({args.interface}:{args.channel}) — zbieram ramki...")
    bus = open_bus(args)
    messages = []
    t_end = time.monotonic() + args.capture
    try:
        while time.monotonic() < t_end:
            msg = bus.recv(timeout=0.2)
            if msg is not None:
                messages.append(msg)
    except KeyboardInterrupt:
        print("# przerwano (użyję zebranych ramek)")
    finally:
        bus.shutdown()
    print(f"# zebrano {len(messages)} ramek")
    return messages


def _generate(args, messages: list, stem: str) -> int:
    if not messages:
        print("# Brak ramek — nic do roboty.")
        return 1

    groups: dict = {}
    for m in messages:
        aid = m.arbitration_id
        ext = bool(getattr(m, "is_extended_id", False))
        key = aid + (0x20000000 if ext else 0)
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"aid": aid, "ext": ext, "frames": [], "times": []}
        g["frames"].append(bytes(m.data))
        ts = getattr(m, "timestamp", None)
        if ts:
            g["times"].append(ts)

    wanted = parse_ids(args.ids) if args.ids else None
    ordered = sorted(groups.values(), key=lambda g: len(g["frames"]), reverse=True)

    entries: list = []
    skipped_short = 0
    for g in ordered:
        if wanted is not None:
            if g["aid"] not in wanted:
                continue
        elif len(entries) >= args.top:
            break
        if len(g["frames"]) < args.min_frames:
            skipped_short += 1
            continue
        dlc = _Count(len(f) for f in g["frames"]).most_common(1)[0][0]
        frames = [f for f in g["frames"] if len(f) == dlc]
        entries.append({
            "aid": g["aid"], "ext": g["ext"], "dlc": dlc, "frames": frames,
            "classes": classify_frames(frames),
            "period": estimate_period(g["times"]) if len(g["times"]) > 1 else None,
        })

    if not entries:
        print("# Za mało danych (żadne ID nie ma wymaganej liczby ramek).")
        return 1

    text = build_dbc(entries, version=__version__, note=Path(stem).name)
    if args.out:
        out_path = resolve_path(args.out)
    else:
        out_path = ROOT / "dbc" / f"auto_{stem}.dbc"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")

    print(f"# auto-DBC: {out_path}")
    print(f"# wiadomości: {len(entries)} (pominięto krótkich: {skipped_short})")
    for e in entries:
        bits = ", ".join(f"b{c.byte} {kind_label(c.kind)}" for c in e["classes"])
        per = f", ~{e['period'] * 1000:.1f} ms" if e.get("period") else ""
        frame_mark = " (29-bit)" if e["ext"] else ""
        print(f"  0x{e['aid']:X}{frame_mark}: {bits}{per}")

    try:
        db = load_dbc(out_path)
    except Exception as exc:  # noqa: BLE001
        print(f"# UWAGA: cantools nie wczytał wygenerowanego pliku: {exc}")
        return 1

    problems = 0
    for e in entries:
        try:
            db.decode_message(e["aid"], e["frames"][-1])
        except Exception as exc:  # noqa: BLE001
            problems += 1
            print(f"# decode 0x{e['aid']:X}: {exc}")
    n_sigs = sum(len(m.signals) for m in db.messages)
    print(f"# walidacja: OK ({len(db.messages)} wiadomości, {n_sigs} sygnałów"
          + (f", problemów: {problems}" if problems else "") + ")")
    if getattr(args, "json", False):
        emit({"ok": True, "file": str(out_path),
              "messages": [{"id": e["aid"], "ext": e["ext"], "dlc": e["dlc"],
                            "classes": [{"byte": c.byte, "kind": c.kind}
                                        for c in e["classes"]]}
                           for e in entries]})
    print("# wczytaj w GUI: sekcja DBC (lista plików) albo: sniff --dbc <plik>")
    return 0


def run(args) -> int:
    json_mode(args)
    if args.capture and args.capture > 0:
        stem = time.strftime("capture_%Y%m%d_%H%M%S")
        return _generate(args, _collect_live(args), stem)
    if not args.log:
        raise SystemExit("Podaj plik logu albo użyj --capture SEK")
    messages = read_log(resolve_path(args.log))
    print(f"# autodbc: {len(messages)} ramek z {args.log}")
    return _generate(args, messages, Path(args.log).stem)
