# ROADMAP — can-toolkit → „miriCAN Studio"

Cel: jedno lokalne narzędzie do pełnego cyklu pracy z magistralą CAN w aucie:
**sniff → analiza → dekodowanie (DBC) → testy na stole → wysyłka / sterowanie**.

Status (2026-10-06):
* **Etap 0 — ZROBIONY** ✅ (sniff/send/replay/selftest, opendbc lokalnie, tryb silent M1)
* **Etap 1 — ZROBIONY** ✅: skaner bitrate (`scan`), diff logów, detekcja
  liczników/sum kontrolnych (v1), konwersje logów (.asc/.blf), profile
  pojazdów (profil **BMW**), modularny pakiet `canstudio`, **ISO-TP/UDS** (v1.0:
  komenda `uds scan|info|read|write|dtc|session|reset|raw`; can-isotp + udsoncan;
  testy `tests/test_uds_virtual.py`).
* **Automatyzacja (2026-10-06)**: ✅ `watch` (detekcja zmian na żywo),
  ✅ `discover` (klasyfikacja: przyciski/sensory/liczniki), ✅ `correlate`
  (znaczniki -> "co reaguje na akcję"), ✅ znaczniki w `sniff --marks`.
* **MITM (2026-10-06)**: ✅ silnik `bridge` (przekazywanie + set/counter/checksum,
  reguły JSON, tryb tap), ✅ demo na magistralach wirtualnych; do zrobienia:
  test na dwóch fizycznych kanałach + konfigurator w GUI.
* **Inspiracje z CAN SHARK (2026-10-06)**: ✅ okresy ramek (`stats` + w
  sniff/watch), ✅ filtry hide/show (`--hide-ids`), ✅ `send` z `--sweep`
  (płynna zmiana bajtu) + auto-licznik/suma, ✅ `bruteforce` (przemiatanie
  ID/wartości/bitów, dry-run + `--yes` tylko na stole), ✅ launcher `START.bat`.
* **Sniffer (2026-10-06)** ✅ (wcześniej „Łowca przycisków") — kreator sesji: ekran pulsuje (podświetlenie
  + opcjonalny dźwięk), użytkownik trzyma przycisk w oknach „TRZYMAJ”; znaczniki
  DOWN/UP w logu, analiza krawędzi (trafienia / powroty / opóźnienie ms / tło)
  i ranking kandydatów. Dodatkowo: naprawiony filtr w Live Trace (pełny re-match:
  ID z „0x” lub bez, nazwy DBC, wiele tokenów).
* **Automatyzacja v0.6 (2026-10-06)** ✅ — pełne wsparcie **11- i 29-bit CAN**
  (kluczowanie std/ext bez kolizji w GUI i analizach), **trigger-nagrywanie
  „±5 s od zmiany”** bajtu (ring buffer + auto-zapis `logs/trigger_*.log`),
  **auto-przypinanie** najlepszego kandydata ze Sniffera do wykresu, **eksport
  wykresów do CSV/PNG**. Auto-DBC: ✅ zrobiony w v1.2 (komenda `autodbc`).
* **GUI — CAN Studio: v0.6** ✅ — lokalna aplikacja webowa (`py -m canstudio gui`
  / `GUI.bat`): live trace (strumień/grupowany, filtr ID/nazw), inspektor ID
  z klasyfikacją bajtów, TX (sweep/licznik/suma), REC + znaczniki, tryb demo,
  **Signal Scope: wiele wykresów naraz** (bajty + sygnały DBC, legenda, eksport),
  **panel Analiza logów** (Przegląd/Diff/Znaczniki), **konfigurator MITM**,
  **Sniffer** (pulsy + analiza krawędzi), **trigger ±5 s**.
* **GUI — Diagnostyka UDS (2026-10-07)** ✅ — panel „Diagnostyka” w Studiu:
  skan ECU, czytanie DID, DTC; read-only; w demo wirtualny sterownik UDS (0x6F1→0x6F9).
* **Auto-DBC (2026-10-07)** ✅ — `autodbc`: klasyfikacja bajtów → wstępny plik
  `.dbc` (z logu albo `--capture`); moduł `canstudio/dbcgen.py`;
  `docs/06-auto-dbc.md`; przykłady `dbc/auto_demo_*.dbc`.
* **Inspektor × DBC + bazy community (2026-10-07)** ✅ — powiązanie klasyfikacji bajtów
  z sygnałami DBC (plakietki, zakresy, ostrzeżenia o nakładaniu na licznik/sumę);
  `dbc/community` (OBD2, BMW E90/E39, J1939, MIT); loader DBC z fallbackiem `strict=False`.
* **Anotacje ID (2026-10-07)** ✅ — nazwy i notatki ID zapisywane w profilu pojazdu
  (`annotations` w `profiles/*.json`); edycja w Inspektorze, wybór profilu w Sesji;
  `docs/07-annotacje.md`.
* **Menedżer logów + trigger (2026-10-07)** ✅ — GUI: statystyki logów, przycinanie
  (trim → `logs/trim_*.log`), odtwarzanie z modyfikacją (reguły jak MITM); CLI `replay`
  z `--set/--counter/--checksum/--drop`; trigger z oknem −/+ i trybem ciągłym;
  `docs/08-przeglad-kodu.md` (przegląd + poprawki).
* **Agent-friendly + MCP (2026-10-07)** ✅ — `--json`/`--jsonl` w 12 komendach + `ctl`
  (REST/WS); **serwer MCP** (15 narzędzi, podłączony do mcporter); `docs/09-agenci.md`.
* **Procedury F1/slice 1 (2026-10-07)** ✅ — ekstraktor sesji UDS z nagrania
  (`isotp_log.py`), kompilator + magazyn (`procedures/`, `mirican-procedure/1`),
  CLI `proc`; plan całości: `docs/10-procedury.md`.
* **OBD przez vLinker MS (2026-10-08) — v2.4** ✅ — ELM327 po BT SPP (`elm327.py`), OBD-II
  (`obd.py`: PID-y/DTC/VIN + sesja), CLI `obd test|info|read|monitor|dtc` (auto-port),
  panel „Diagnostyka OBD” + szkielet „Logger OBD” w GUI (`/api/obd/*`), sesje `obd-logger/1`
  (`obd_log.py`: zapis/statystyki/serie/pobieranie z ESP32 po WiFi); testy 13+4; `docs/12-obd-vlinker.md`.
* **Wersjonowanie (2026-10-06)**: wydania numerowane co 0.1 (0.1…0.9, potem
  1.0, 1.1…); bieżące: **v2.4** — OBD (vLinker): `obd` + panel GUI + szkielet loggera; wcześniej v2.3: Procedury F1/slice 1; v2.2: panel AGENT (MCP)
  w docku; v2.1: serwer MCP + podłączenie agenta (mcporter); v2.0: wsparcie agentowe
  (--json/--jsonl + ctl); v1.9: trzeci panel + naprawy łączenia; v1.8: uchwyty resize;
  v1.7: separatory; v1.6: dock; v1.5: menedżer logów + trigger; v1.4: anotacje;
  v1.3: Inspektor × DBC; v1.2: auto-DBC + panel UDS; v1.1: panel Diagnostyka;
  v1.0: ISO-TP/UDS; v0.9: Sniffer v2.

---

## Etap 1 — Rdzeń analityczny (najbliższe iteracje, CLI)

1. **Skaner magistrali** — auto-detekcja prędkości (500k/250k/125k/100k/83k)
   i trybu (normal/silent); raport „co słychać" na każdym bitrate.
2. **Analiza różnicowa (diff)** — porównanie dwóch nagrań / trybów pracy:
   które ID i które bajty się zmieniają (heatmapa, top zmian). Klasyczna technika
   „wcisnąłem przycisk → zobacz, co skoczyło".
3. **Detektor liczników i sum kontrolnych** — heurystyka: który bajt to rolling
   counter, który to checksum; moduł obliczeń (XOR, sum8, CRC8/CRC16 — warianty).
   Bez tego nie da się wiarygodnie odtwarzać ramek sterujących.
4. **Formaty plików** — eksport/import `.asc` i `.blf` (SavvyCAN, BusMaster, Wireshark).
5. ✅ **ISO-TP + UDS** — skaner ECU, odczyt DTC, odczyt/zapis DID, sesje diagnostyczne
   (często „legalna" droga sterowania funkcjami modułów). **ZROBIONE (v1.0)**:
   `py -m canstudio uds …`, `docs/05-uds.md`, testy `tests/test_uds_virtual.py`.
6. **Profile pojazdów** (YAML/JSON) — bitrate, DBC, znane ID, notatki, makra TX.

## Etap 2 — GUI: „CAN Studio" (lokalna aplikacja webowa)

- **Live Trace** — strumień ramek z filtrami, kolorami per-ID, pauzą i statystykami.
- **Dekodowanie** — tabela sygnałów z DBC + wykresy czasowe (uPlot), przypinane
  sygnały, „gauge".
- **Panel TX** — edycja ramek, wysyłka cykliczna, makra i „przyciski akcji".
- ✅ **Menedżer logów** — nagrywanie, odtwarzanie (z modyfikacją), przycinanie, statystyki (v1.5).
- **Widok zmian** — byte-diff na żywo ✅ (podświetlanie zmienionych bajtów); liczniki/checksum w Inspektorze.
- ✅ **Anotacje** — nazwy ID, komentarze, zapis do profilu pojazdu (v1.4).

## Etap 3 — Warsztat zaawansowany

- **Bench twin** — symulator ECU: odtwarzanie z modyfikacją i automatyczne
  odpowiedzi (testy modułów poza autem).
- **Skaner funkcji** — sterowany fuzzing (tylko bench, limity, pełny log).
- **Nauka sygnałów** — korelacja Twoich akcji (etykiety) z bajtami ramek.
- **CAN FD** — pełne wsparcie (po przejściu na candlelight).
- **Biblioteka pojazdów** — import/eksport profili.

---

## Stack (w czym budujemy)

| warstwa | technologia | dlaczego |
|---|---|---|
| transport CAN | **python-can** (slcan teraz; gs_usb/pcan później) | działa z MKS od ręki |
| dekodowanie | **cantools** + lokalne DBC (opendbc) | standard w świecie CAN |
| diagnostyka | **python-can-isotp + udsoncan** | gotowe UDS/ISO-TP |
| analiza | **numpy** | liczniki/checksumy, korelacje |
| GUI backend | **FastAPI + WebSocket** | lekki lokalny serwer, streaming |
| GUI frontend | **HTML/CSS/JS + uPlot** | ładny wygląd, bez node/npm, mały footprint |
| okno desktop (opcja) | pywebview | „appka" bez przeglądarki |
| dane | pliki candump + SQLite (projekty/annotacje) | proste, przenośne |

## Dopracowanie

**Funkcjonalność:**
- pytest + magistrala wirtualna (testy bez sprzętu) — ✅ pierwszy zestaw:
  `tests/test_uds_virtual.py` (UDS); nagrania jako testy regresyjne
- stanowisko testowe: **ESP32 jako drugi węzeł CAN** (toolchain już jest;
  np. moduł MCP2515 lub TWAI) — do testów ACK, wysyłki i symulacji ECU
- walidacja krzyżowa dekodowań: cabana / Cangaroo / SavvyCAN
- dane referencyjne: commaCarSegments, logi z Twoich sesji

**Wygląd (UX/UI):**
- design system: ciemny motyw „warsztatowy", mono fonty do hex, kolory per-ID
- 2–3 kierunki wizualne do wyboru przed implementacją
- iteracje na zrzutach ekranu (podgląd na żywo) + Twoje uwagi
- testy czytelności na prawdziwych logach (duże strumienie, 2000+ ramek/s)

## Zasady bezpieczeństwa
- Wysyłka: tylko postój / bench; fuzzing tylko bench; log każdej wysłanej ramki.
- Najpierw nasłuch i analiza, potem dopiero TX.
- Dysk C: mało miejsca → lekkie zależności, cięższe dane ewentualnie na D:.
