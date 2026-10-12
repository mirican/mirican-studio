#!/usr/bin/env py
"""CAN Studio — prosty launcher (menu tekstowe).

Uruchomienie:
* dwuklik na ``START.bat`` w katalogu can-toolkit, albo
* ``py start_menu.py``

Launcher sam sprawdza zależności (i doinstaluje je w razie potrzeby) oraz
wykrywa port Canable (USB 16D0:117E).
"""

from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

MENU = """
=== miriCAN Studio — launcher ===

 MAGISTRALA NA ŻYWO
  1) Skanuj magistralę (jaka prędkość?)          [scan]
  2) Nasłuch + log                               [sniff]
  3) Nasłuch z auto-detekcją zmian               [watch]
  4) Nagrywanie ze znacznikami                   [sniff --marks]
  5) Wyślij ramkę / sweep                        [send]
  6) Odtwórz log na magistralę                   [replay]

 WYSYŁKA / MITM  (BENCH)
  7) Man in the middle                           [bridge]
  8) Bruteforce / poke (tylko stół!)             [bruteforce]

 ANALIZA LOGÓW (offline)
  9) Tabela per ID + okresy                      [stats]
 10) Co się zmieniło? (diff)
 11) Co reaguje na przycisk? (correlate)
 12) Klasyfikacja bajtów (discover)
 13) Liczniki i sumy (checksum)

 INNE
 14) Porty COM                                   [ports]
 15) Test sprzętu                                [selftest]

 GUI (główny program)
 16) miriCAN Studio — interfejs graficzny        [gui]

 DIAGNOSTYKA UDS (postój / ławka testowa; opcjonalnie: can-isotp+udsoncan)
 17) Skan ECU — szukaj sterowników               [uds scan]
 18) Rozpoznaj sterownik (VIN, numery, wersje)   [uds info]
  0) Wyjście
"""


def ensure_deps() -> bool:
    import importlib.util

    def have(name):
        return importlib.util.find_spec(name) is not None

    if not all(have(m) for m in ("can", "cantools", "serial")):
        print("Brakujące zależności — instaluję (python-can, cantools, pyserial)...\n")
        try:
            rc = subprocess.call([sys.executable, "-m", "pip", "install", "-r",
                                  os.path.join(HERE, "requirements.txt")])
        except Exception as exc:  # noqa: BLE001
            print(f"Błąd instalacji: {exc}")
            return False
        if rc != 0:
            return False
    if not all(have(m) for m in ("isotp", "udsoncan")):
        print("Info: brak can-isotp/udsoncan — diagnostyka UDS niedostępna "
              "(py -m pip install can-isotp udsoncan)\n")
    return True


def detect_port() -> str:
    try:
        from serial.tools import list_ports
        ports = list(list_ports.comports())
    except Exception:
        return ""
    for p in ports:
        if p.vid == 0x16D0 and p.pid == 0x117E:  # Canable (slcan)
            return p.device
    for p in ports:
        if p.description and "USB" in p.description:
            return p.device
    return ports[0].device if ports else ""


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def run_tool(arguments) -> None:
    print()
    try:
        subprocess.call([sys.executable, "-m", "canstudio"] + arguments, cwd=HERE)
    except KeyboardInterrupt:
        pass
    print()


def main() -> int:
    if not ensure_deps():
        input("Nie udało się przygotować zależności. Enter zamyka...")
        return 1

    port = detect_port()
    while True:
        print(MENU)
        print(f"Wykryty port: {port or '(brak — wpisz ręcznie)'}")
        try:
            choice = input("Wybór: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if choice in ("0", "q", "quit", "exit", "wyjdz", "wyjdź"):
            return 0

        if choice == "1":
            run_tool(["scan", "--channel", ask("Port COM", port), "--per-rate", "1.0"])

        elif choice == "2":
            args = ["sniff", "--channel", ask("Port COM", port)]
            prof = ask("Profil (np. bmw, Enter = brak)")
            if prof:
                args += ["--profile", prof]
            run_tool(args)

        elif choice == "3":
            args = ["watch", "--channel", ask("Port COM", port)]
            prof = ask("Profil (np. bmw, Enter = brak)")
            if prof:
                args += ["--profile", prof]
            run_tool(args)

        elif choice == "4":
            run_tool(["sniff", "--channel", ask("Port COM", port), "--marks"])
            print("(w trakcie: ENTER = znacznik, tekst+ENTER = etykieta)")

        elif choice == "5":
            args = ["send", "--channel", ask("Port COM", port),
                    "--id", ask("ID ramki (np. 0x130)"),
                    "--count", ask("Ile razy", "1"),
                    "--interval", ask("Odstęp [s]", "0.1")]
            data = ask("Dane hex (Enter = puste)")
            if data:
                args += ["--data", data]
            sweep = ask("Sweep (np. 3:0-255, Enter = brak)")
            if sweep:
                args += ["--sweep", sweep]
            counter = ask("Auto-licznik, bajt (Enter = brak)")
            if counter:
                args += ["--counter", counter]
            checksum = ask("Auto-suma, BAJT:ALGO (np. 7:xor8, Enter = brak)")
            if checksum:
                args += ["--checksum", checksum]
            if ask("Na sucho? [t/n]", "t").lower() == "t":
                args += ["--dry-run"]
            run_tool(args)

        elif choice == "6":
            run_tool(["replay", "--channel", ask("Port COM", port), ask("Plik logu")])

        elif choice == "7":
            if ask("Demo [d] / dwa kanały [k]", "d").lower() == "d":
                run_tool(["bridge", "--demo"])
            else:
                args = ["bridge", "--in", ask("Kanał A (np. slcan:COM7)"),
                        "--out", ask("Kanał B (np. slcan:COM8)")]
                set_r = ask("Ustaw bajt ID:B=VAL (Enter = brak)")
                if set_r:
                    args += ["--set", set_r]
                cnt = ask("Licznik ID:BAJT (Enter = brak)")
                if cnt:
                    args += ["--counter", cnt]
                chk = ask("Suma ID:BAJT:ALGO (Enter = brak)")
                if chk:
                    args += ["--checksum", chk]
                if ask("Tryb TAP, tylko podgląd? [t/n]", "t").lower() == "t":
                    args += ["--tap"]
                run_tool(args)

        elif choice == "8":
            mode = ask("Tryb ids/values/bits", "ids")
            args = ["bruteforce", "--channel", ask("Port COM", port), "--mode", mode]
            if mode == "ids":
                args += ["--from", ask("ID od", "0x000"), "--to", ask("ID do", "0x7FF")]
            else:
                args += ["--id", ask("ID ramki (np. 0x2CA)"), "--byte", ask("Bajt", "0")]
                if mode == "values":
                    vals = ask("Wartości (Enter = 00-FF)")
                    if vals:
                        args += ["--values", vals]
            if ask("Potwierdź nadawanie — wpisz TAK").strip() == "TAK":
                args += ["--yes"]
            run_tool(args)

        elif choice == "9":
            run_tool(["stats", ask("Plik logu")])

        elif choice == "10":
            run_tool(["diff", ask("Log A (bazowy)"), ask("Log B (po zmianie)")])

        elif choice == "11":
            run_tool(["correlate", ask("Log ze znacznikami")])

        elif choice == "12":
            run_tool(["discover", ask("Plik logu")])

        elif choice == "13":
            args = ["checksum", ask("Plik logu")]
            only = ask("Tylko ID (Enter = auto)")
            if only:
                args += ["--id", only]
            run_tool(args)

        elif choice == "14":
            run_tool(["ports"])

        elif choice == "15":
            run_tool(["selftest", "--port", ask("Port COM", port)])

        elif choice == "17":
            run_tool(["uds", "scan", "--channel", ask("Port COM", port)])

        elif choice == "18":
            args = ["uds", "info", "--channel", ask("Port COM", port),
                    "--txid", ask("ID sterownika (hex, np. 6F1)")]
            sess = ask("Sesja przed odczytem (hex, Enter = brak)")
            if sess:
                args += ["--session", sess]
            run_tool(args)

        elif choice in ("16", "g", "gui"):
            run_tool(["gui"])

        else:
            print("Nieznany wybór.\n")


if __name__ == "__main__":
    sys.exit(main())
