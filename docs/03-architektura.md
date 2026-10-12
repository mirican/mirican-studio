# Architektura canstudio

## Struktura pakietu

```
can-toolkit/
├── canstudio/                 # pakiet (logika + CLI)
│   ├── bus.py                 # rejestr interfejsów (@bus_factory), Canable2SlcanBus (tryb M1), porty
│   ├── frames.py              # Frame, format/parse candump, parse_id(s)
│   ├── logio.py               # odczyt/zapis logów: candump, .asc, .blf
│   ├── dbc.py                 # cantools: wczytywanie i dekodowanie DBC
│   ├── checksums.py           # detekcja liczników/sum kontrolnych + kalkulatory (XOR/SUM/CRC8)
│   ├── detect.py              # detekcja zmian na żywo + klasyfikacja bajtów
│   ├── markers.py             # znaczniki w logach + korelacja zdarzeń
│   ├── bridging.py            # silnik MITM (przekazywanie + modyfikacje + demo)
│   ├── buttonfinder.py        # szukacz przycisku (analiza sesji pulsów DOWN/UP)
│   ├── diffing.py             # porównywanie dwóch logów
│   ├── stats.py               # IdStats, grupowanie bajtów per ID
│   ├── config.py              # ścieżki, profile pojazdów, resolve_args (--profile)
│   ├── cli.py                 # `py -m canstudio <narzędzie>` (rejestr Tools)
│   ├── tools/                 # narzędzia CLI (każde w osobnym pliku)
│   └── gui/                   # miriCAN Studio GUI (FastAPI + WebSocket + index.html)
│       ├── sniff.py           # nasłuch + log + dekodowanie
│       ├── watch.py           # nasłuch z auto-detekcją zmian
│       ├── discover.py        # klasyfikacja bajtów (przyciski/sensory/liczniki)
│       ├── correlate.py       # korelacja znaczników ("co reaguje na akcję")
│       ├── bridge.py          # MITM między dwoma kanałami
│       ├── bruteforce.py      # bench: przemiatanie ID/wartości/bitów
│       ├── stats.py           # okresy/częstotliwości per ID
│       ├── scan.py            # skaner bitrate
│       ├── send.py            # wysyłka ramek
│       ├── replay.py          # odtwarzanie logów
│       ├── diff.py            # porównanie logów
│       ├── checksum.py        # analiza liczników/sum
│       ├── convert.py         # konwersje formatów logów
│       ├── profile.py         # profile pojazdów
│       └── selftest.py        # testy (offline + sprzętowe)
├── profiles/                  # profile pojazdów (JSON)
├── dbc/                       # lokalne bazy DBC (opendbc, tesla_model3, example.dbc)
├── logs/                      # nagrania (candump)
├── design/                    # makiety UI (miriCAN Studio)
├── START.bat / start_menu.py  # launcher (menu, auto-detekcja portu)
├── GUI.bat                    # dwuklik → CAN Studio w przeglądarce
└── wrappery: sniff.py, send.py, replay.py, selftest.py (stare wywołania)
```

## Jak dodać nowe narzędzie

1. Utwórz `canstudio/tools/moje_narzedzie.py`:

   ```python
   NAME = "moje"
   HELP = "Krótki opis w pomocy"

   def add_arguments(parser):
       ...  # argparse: add_argument(...)

   def run(args) -> int:
       ...
       return 0
   ```

2. Dopisz moduł do listy `TOOLS` w `canstudio/tools/__init__.py`.

3. Gotowe: `py -m canstudio moje ...` (+ wpis w pomocy).

## Jak dodać nowy interfejs magistrali

W `canstudio/bus.py`:

```python
@bus_factory("mojinterfejs")
def _build_moj(args):
    import mojsterownik
    return mojsterownik.open(channel=args.channel, bitrate=args.bitrate)
```

Pojawi się automatycznie w `--interface` wszystkich narzędzi.
Nazwy interfejsów wspierających tryb silent: slcan (M1 dla canable2 / L dla innych).

## Profile pojazdów (`profiles/*.json`)

```json
{
  "name": "bmw",
  "description": "...",
  "bitrate": 500000,
  "dbc": "dbc/opendbc/bmw_e9x_e8x.dbc",
  "bus_hint": "...",
  "notes": ["..."]
}
```

Użycie: `py -m canstudio sniff --profile bmw --channel COM7`
(profil ustawia m.in. bitrate i DBC; argumenty CLI mają pierwszeństwo).

## Testy

* `py -m canstudio selftest` — testy offline (format, DBC, pętla wirtualna,
  detekcja liczników/sum, diff),
* `py -m canstudio selftest --port COM7` — + test sprzętowy,
* dane regresyjne: prawdziwe logi w `logs/` → `canstudio diff`, `canstudio checksum`,
  `canstudio replay` na magistrali wirtualnej.

## Konwencje

* Narzędzia nie drukują w losowych miejscach — wynik czytelny, linie komentarzy
  zaczynają się od `#`.
* Logi zapisujemy w formacie `candump -L` (najprostsza wymiana między narzędziami).
* Wysyłka/replay: zawsze komunikat ostrzegawczy; przyszły GUI pokaże to samo.
