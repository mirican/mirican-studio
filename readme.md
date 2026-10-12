# can-toolkit → miriCAN Studio

Narzędzia do rozgryzania (i sterowania) urządzeniami CAN w samochodzie.
Rdzeń w Pythonie (`python-can` + `cantools`), spakowany w modularny pakiet
`canstudio` — łatwo dokładać funkcje i interfejsy.

**Najszybszy start (GUI):** dwuklik na **`GUI.bat`** → otwiera **miriCAN Studio**
w przeglądarce (live trace, TX, REC — także tryb demo bez sprzętu).
Alternatywnie: `py -m canstudio gui` albo menu w `START.bat` (pozycja 16).

Możliwości:

* **gui** — miriCAN Studio: lokalna aplikacja webowa (live trace strumień/grupowany
  z filtrem ID/nazwy, inspektor ID + panel analizy u dołu (klasyfikacja bajtów, sygnały DBC), TX z opcjami zaawansowanymi,
  REC + znaczniki, **wykresy wielu sygnałów** z eksportem CSV/PNG, **panel Analiza**
  (Przegląd/Diff/Znaczniki), **konfigurator MITM**, **Sniffer**
  (sesja pulsów + analiza krawędzi), **trigger ±5 s przy zmianie** (v1.5: okno −/+ i tryb ciągły), **panel Diagnostyka (UDS)**,
  **anotacje ID (profil pojazdu)**, **menedżer logów (statystyki/przycinanie/replay z modyfikacją)**, tryb demo (z wirtualnym sterownikiem UDS);
  pełne wsparcie **11- i 29-bit CAN**; serwer sam się zamyka po zamknięciu GUI
  (zwalnia port COM))
* **sniff** — nasłuch + log (candump) + dekodowanie DBC na żywo
* **scan** — skaner prędkości magistrali (500k/250k/125k/…)
* **send** — wysyłanie ramek (pojedynczo / cyklicznie)
* **replay** — odtwarzanie nagrań z regulacją tempa
* **diff** — porównanie dwóch logów („co się zmieniło przy tej akcji")
* **checksum** — detekcja liczników i sum kontrolnych (XOR/SUM/CRC8)
* **watch** — nasłuch z automatyczną detekcją zmian (przyciski, flagi, zdarzenia)
* **discover** — klasyfikacja bajtów: stały / licznik / suma / przełącznik / sensor
* **correlate** — automatyczne „co reaguje na przycisk?" (ze znaczników `sniff --marks`)
* **bridge** — man-in-the-middle: przekazywanie i modyfikacja ramek (2 kanały)
* **bruteforce** — (bench) przemiatanie ID / wartości / bitów z nasłuchem reakcji
* **stats** — tabela per ID: okres [ms], częstotliwość, ostatnie dane
* **convert** — konwersje logów (candump ↔ .asc, odczyt .blf)
* **profile** — profile pojazdów (na start: **BMW**)
* **selftest** — testy (offline + sprzętowe)
* **autodbc** — auto-DBC: wstępny plik .dbc z logu/nasłuchu (klasyfikacja bajtów → sygnały)
* **uds** — diagnostyka UDS/ISO-TP: panel w GUI + komenda CLI (skaner ECU,
  odczyt/zapis DID, kody DTC, sesje; dodatkowe pakiety: `can-isotp`, `udsoncan`;
  szczegóły `docs/05-uds.md`)
* **obd** — diagnostyka OBD-II przez adapter ELM327 (np. **vLinker MS** po Bluetooth):
  test łącza, PID-y (odczyt/monitor z zapisem sesji), DTC (odczyt/kasowanie), VIN;
  auto-detekcja portu; panel w GUI + szkielet zakładki „Logger OBD”; szczegóły `docs/12-obd-vlinker.md`
* **vin** — dekoder VIN: marka/kraj/rok, model/seria (Mercedes), silnik (PSA),
  platforma (VAG), suma kontrolna (norma NA); zakres dekodowania per marka: `docs/13-vin.md`
* **ctl** — sterowanie działającym Studiem po REST/WS (JSON; dla agentów i skryptów;
  tryby `--json`/`--jsonl` też w pozostałych komendach; `docs/09-agenci.md`)
* **mcp** — serwer MCP (stdio) dla agentów: `can_*` (analiza/UDS) + `gui_*` (Studio);
  15 narzędzi; zintegrowany z mcporter (`mirican-studio`)
* **proc** — procedury: nagranie sesji diagnostycznej → mini-program (`procedures/*.json`);
  `proc list|extract|show|rm` (szczegóły: `docs/10-procedury.md`)

## Szybki start (Windows)

Wymagania: Python 3.11+ (`py`), Canable w trybie **slcan** (nasz MKS: COM7).

```powershell
cd <folder projektu>\can-toolkit
py -m pip install -r requirements.txt
py -m canstudio ports                 # porty COM
py -m canstudio selftest              # test offline
py -m canstudio selftest --port COM7  # test sprzętowy
```

Typowy przepływ (przykład BMW):

```powershell
py -m canstudio scan --channel COM7                    # jaka prędkość magistrali?
py -m canstudio sniff --channel COM7 --profile bmw     # nasłuch + DBC (E9x/E8x)
py -m canstudio sniff --channel COM7 --silent          # nasłuch bierny (M1)
py -m canstudio diff logs\przed.log logs\po.log        # co się zmieniło?
py -m canstudio checksum logs\po.log --id 0x130        # licznik / suma kontrolna
py -m canstudio send --channel COM7 --id 0x123 --data "DE AD BE EF"
py -m canstudio send --channel COM7 --id 0x130 --data "03 00 10 00 80 00 00 00" --sweep 3:0-255 --counter 1 --checksum 7:xor8 --count 50
py -m canstudio replay --channel COM7 logs\demo_sample.log
py -m canstudio replay --channel COM7 logs\auto_demo_b.log --rate 2 --set "0x130:3=0x2A" --counter 0x130:1 --checksum 0x130:7:xor8

# Automatyzacja (przyciski / parametry):
py -m canstudio watch --channel COM7 --silent          # tylko ciekawe zmiany
py -m canstudio sniff --channel COM7 --marks           # ENTER / tekst+ENTER = znaczniki
py -m canstudio correlate logs\sniff_20261006.log      # co reaguje na akcję?
py -m canstudio discover logs\sniff_20261006.log       # klasyfikacja bajtów
py -m canstudio autodbc logs\sniff_20261006.log        # wstępny plik DBC z logu

# Man in the middle (2 interfejsy; demo bez sprzętu):
py -m canstudio bridge --demo
py -m canstudio bridge --in slcan:COM7 --out slcan:COM8 --set "0x130:3=0x2A" --counter 0x130:1 --checksum 0x130:7:xor8

# Diagnostyka UDS/ISO-TP (tylko postój/ławka; wymaga can-isotp+udsoncan):
py -m canstudio uds scan --channel COM7                  # szukaj sterowników (TesterPresent 3E00)
py -m canstudio uds info --channel COM7 --txid 6F1       # VIN, numery seryjne, wersje (DID F190, F18C…)
py -m canstudio uds read --channel COM7 --txid 6F1 F190 F18C
py -m canstudio uds dtc  --channel COM7 --txid 6F1 --session 3

# Bench / statystyki:
py -m canstudio bruteforce --channel COM7 --from 0x700 --to 0x7FF        # dry-run (bez --yes)
py -m canstudio stats logs\sniff_20261006.log                           # okresy per ID
```

Stare wywołania działają przez wrappery: `py sniff.py ...`, `py send.py ...`,
`py replay.py ...`, `py selftest.py ...` (przekierowują do `py -m canstudio ...`).

## Struktura

```
can-toolkit/
├── canstudio/          # pakiet: bus, frames, logio, dbc, diag (UDS), checksums, diffing, tools/
├── profiles/           # profile pojazdów (bmw.json)
├── dbc/                # opendbc (58) + tesla_model3 + community (OBD2/BMW/J1939) + auto_*
├── logs/               # nagrania (candump -L) + logi UDS + próbki demo
├── tests/              # testy syntetyczne (magistrala wirtualna, bez sprzętu)
├── design/             # makieta GUI „CAN Studio"
├── docs/               # 01 sprzęt, 02 zasoby DBC, 03 architektura, 04 MITM, 05 UDS
└── wrappery: sniff.py / send.py / replay.py / selftest.py
```

## Interfejsy CAN

| interface | opis |
|---|---|
| `slcan` (domyślnie) | Canable po COM (CDC), bez sterowników |
| `gs_usb` | candleLight (na Windows wymaga pyusb + WinUSB/Zadig) |
| `pcan` | adaptery PEAK |
| `virtual` | pętla testowa bez sprzętu |
| `socketcan` | Linux `can0` |

Nowy interfejs dodajesz jedną funkcją `@bus_factory("nazwa")` w
`canstudio/bus.py` — od razu pojawia się we wszystkich narzędziach.
Szczegóły: `docs/03-architektura.md`.

## Bezpieczeństwo

* Najpierw nasłuch, wysyłka tylko na postoju / na stole.
* Nie ruszaj ramek airbag / hamulców / kierownicy.
* Logi zapisuj zawsze — łatwiej wrócić do analizy.
* Wpięcie w auto: OBD-II 6=CAN-H, 14=CAN-L, 4/5=GND; terminacja adaptera OFF.

## Dokumentacja i linki

* `docs/01-canable-windows.md` — sprzęt MKS CANable 2.0 PRO, tryby, flashowanie.
* `docs/02-zasoby-dbc.md` — bazy CAN producentów, narzędzia, fora.
* `docs/03-architektura.md` — jak rozbudowywać (narzędzia, interfejsy, profile).
* `docs/04-mitm.md` — man-in-the-middle: koncepcja, reguły, przykłady.
* `docs/05-uds.md` — diagnostyka UDS/ISO-TP: komendy, przykłady, bezpieczeństwo.
* `docs/06-auto-dbc.md` — auto-DBC: wstępny plik .dbc z logu/nasłuchu.
* `docs/07-annotacje.md` — nazwy i notatki ID w profilu pojazdu.
* `docs/08-przeglad-kodu.md` — przegląd kodu i refaktoryzacja (ocena + poprawki).
* `docs/09-agenci.md` — sterowanie agentowe: `--json`/`--jsonl` + `ctl`.
* `docs/12-obd-vlinker.md` — diagnostyka OBD-II przez adapter ELM327 (vLinker MS).
* `docs/13-vin.md` — dekoder VIN: co da się ustalić per marka (research + źródła).
* `docs/14-github.md` — przygotowanie do publikacji na GitHub (audyt + checklista).
* `ROADMAP.md` — plan rozwoju (Etap 1 zrobiony ✅, Etap 2 — GUI w toku).
* python-can: https://python-can.readthedocs.io • cantools: https://github.com/cantools/cantools
