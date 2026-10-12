"""Narzedzie: vin - dekoder VIN (marka, kraj, rok, model/seria, silnik).

Przyklady:
  py -m canstudio vin WDD2073221F000000
  py -m canstudio vin VF3AB5FS0A0000001 --json
"""

from __future__ import annotations

import argparse

from ..json_cli import add_json_args, emit, json_mode
from ..vin import decode_vin

NAME = "vin"
HELP = "Dekoder VIN: marka, kraj, rok, model/seria, silnik (gdzie dostępne)"


def run(args) -> int:
    json_mode(args)
    dec = decode_vin(args.vin)
    if getattr(args, "json", False):
        emit(dec)
        return 0 if dec.get("ok") else 1
    if not dec.get("ok"):
        print(f"# {dec.get('error', 'blad')}")
        return 1
    print(f"# VIN: {dec['vin']}")
    if dec.get("brand"):
        extra = ", ".join(x for x in (dec.get("manufacturer"), dec.get("country")) if x)
        print(f"  marka: {dec['brand']}" + (f"  ({extra})" if extra else ""))
    else:
        print(f"  marka: (nieznany WMI {dec.get('wmi')})"
              + (f"  (kraj: {dec['country']})" if dec.get("country") else ""))
    if dec.get("region"):
        print(f"  region: {dec['region']}")
    if dec.get("model"):
        m = dec["model"]
        print("  model/seria: " + (f"{m['name']} (kod {m['code']})" if m.get("name")
                                   else f"kod {m['code']}"))
    if dec.get("platform"):
        print(f"  platforma: {dec['platform']['name']} ({dec['platform']['code']})")
    if dec.get("engine"):
        print(f"  silnik: {dec['engine']['name']} (kod {dec['engine']['code']})")
    if dec.get("year_likely"):
        alt = [y for y in (dec.get("year_candidates") or []) if y != dec["year_likely"]]
        tail = f"; mozliwe tez: {', '.join(map(str, alt))}" if alt else ""
        print(f"  rok: {dec['year_likely']} (kod {dec['year_code']}{tail})")
    if dec.get("plant_name"):
        print(f"  fabryka: {dec['plant_name']} (kod {dec['plant']})")
    else:
        print(f"  fabryka: kod {dec.get('plant')}")
    cd = dec.get("check_digit") or {}
    if cd.get("applicable"):
        print(f"  suma kontrolna: {'OK' if cd.get('valid') else 'NIEZGODNA'} (poz. 9)")
    for n in dec.get("extra_notes") or []:
        print(f"  - {n}")
    return 0


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("vin", help="numer VIN (17 znaków)")
    add_json_args(parser)
