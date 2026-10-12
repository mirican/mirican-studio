# HANDOFF — miriCAN Studio (2026-10-07)

**Ten plik jest przewodnikiem dla nowego czatu.** Przeczytaj w całości przed pracą.

## 1. Co to jest

Kompletny toolkit CAN (sniff / decode / reverse-engineering / TX / MITM) dla Windows
+ MKS CANable 2.0 PRO. UI: lokalny web GUI „miriCAN Studio".
Projekt: `<folder projektu>\can-toolkit`.
Wersja bieżąca: **v2.4** (numer w nagłówku UI; numeracja +0.1 na wydanie, po 0.9 → 1.0).
Etap 1 domknięty; v2.4 = OBD przez vLinker MS (warstwa ELM327 + komenda `obd`, panel „Diagnostyka OBD”
i szkielet zakładki „Logger OBD” w GUI). Wcześniej v2.3 = Procedury F1/slice 1 (ekstraktor sesji UDS z nagrania + kompilator + CLI `proc`).

Projekty pokrewne: `../obd-logger/` — logger OBD (ESP32-P4+C6, firmware w Arduino;
patrz `obd-logger/handoff.md`; ocena w `docs/11-logger.md`).

## 2. Uruchamianie (dla użytkownika)

- Dwuklik: `GUI.bat` — odpala serwer + przeglądarkę; sam się zamyka po ~30 s bez klienta (zwalnia COM)
- Menu: `START.bat` (18 opcji: 17 = uds scan, 18 = uds info)
- Ręcznie: `py -m canstudio gui` → http://127.0.0.1:8077 (auto-port; `--idle-exit N`, `--no-browser`)
- Po zmianach w kodzie UI → **F5** w przeglądarce

## 3. Sprzęt / środowisko

- MKS CANable 2.0 PRO, firmware normaldotcom/canable2 (slcan), USB VID:PID `16D0:117E` → zwykle **COM7**
  (sprawdź: `py -m canstudio ports`); tryb bierny `--silent` = komenda M1
- Python: **`py`** (3.14; NIE `python` z AutoClaw). Zależności zainstalowane:
  python-can, cantools, fastapi, uvicorn, websockets, can-isotp, udsoncan
- Test sprzętu: `py -m canstudio selftest --port COM7` (8/8 PASS)

## 4. Komendy CLI

`py -m canstudio sniff|watch|scan|send|replay|bridge|bruteforce|diff|correlate|checksum|discover|autodbc|stats|convert|profile|ports|selftest|uds|obd|vin|ctl|mcp|proc|gui`

## 5. GUI — funkcje (stan v0.9)

- **Live Trace** (Stream / Grupowany, filtr, hide), FREQ per ID
- **Inspektor**: kafelki — RAMKA (neutralny) / KLASYFIKACJA BAJTÓW (niebieski) /
  SYGNAŁY DBC (złoty; legenda „＋ dodaje do wykresu · ✓ usuwa") / TRIGGER ±5s
  — v1.3: kafelki powiązane (plakietki sygnałów przy bajtach — klik podświetla; span+klasa przy
  sygnałach; ⚠ przy nakładaniu na licznik/sumę; linia „poza DBC: bX")
- **Signal Scope**: bajty + sygnały DBC (przypinanie przez ＋/✓), eksport CSV/PNG, ✦ auto bajt
- TX panel (arm / sweep / licznik / suma kontrolna), REC + MARK, **Sniffer**, MITM, Analiza (Przegląd/Diff/Znaczniki)
- Demo: `#demo=1` (wirtualna magistrala, w tym 29-bit `0x18DAF110`);
  stany przez hash, np. `#demo=1&dbc=demo_gui&select=0x130&pins=0x130:EngineSpeed`
- 3 motywy; reprezentacja extended CAN: key = aid + 0x20000000 (wszędzie spójnie)
- **Diagnostyka (UDS)** — panel: Skanuj ECU / Czytaj DID / Odczytaj DTC / Zapis DID / Kasuj DTC
  (zapis i kasowanie za checkboxem „potwierdzam”); live trace pauzuje na czas operacji;
  hash: `#modal=uds&udids=…&udrun=1&udread=1` (auto-run tylko w demo)
- **Diagnostyka OBD (vLinker)** — panel: Połącz/Rozłącz/Test (auto-port adaptera), odczyt PID-ów,
  monitor na żywo (opcjonalny zapis sesji `logs/obd_*.jsonl`), VIN + wspierane PID-y, DTC
  (odczyt; kasowanie za checkboxem); zdarzenia przez WS; `docs/12-obd-vlinker.md`
- **Logger OBD** — zakładka (szkielet): Ustawienia (PID-y/interwał/źródło; `config/logger.json`),
  Odczyt danych (sesje lokalne + pobieranie z loggera ESP32 po WiFi), Analiza (statystyki + wykres)
- **Anotacje** — nazwa + notatka ID zapisywane do profilu pojazdu (`profiles/*.json`);
  edycja w Inspektorze (karta RAMKA), wybór profilu: zakładka Sesja; `docs/07-annotacje.md`
- **Logi** — menedżer logów: Statystyki (ramki/ID/czas/top z okresami), Przytnij (zakres/offset/liczba → `logs/trim_*.log`),
  Odtwarzanie z modyfikacją (drop/ustaw/licznik/suma; tempo/pętla/limit; potwierdzenie na realnych portach); hash: `#modal=log…`
- **Dock analizy (u dołu ekranu)** — 3 panele: KLASYFIKACJA BAJTÓW / SYGNAŁY (DBC) /
  AGENT (MCP) — status i „📋 kopiuj konfigurację”; zwijanie ▾/▸, separatory, stan w localStorage;
  prawa kolumna: RAMKA + TRIGGER

## 6. Sniffer (v0.9) — jak działa

- Sesja pulsów (markery DOWN/UP) → analiza **bajtów i bitów**, tło modelowe + **empiryczne**
  (próbkowanie losowych okien), **pewność** (🟢 ≥70 / 🟡 40–69 / ⚪ <40), rozrzut opóźnienia ±ms,
  auto-przypinanie tylko pewnych trafień
- Plik: `canstudio/buttonfinder.py`; test syntetyczny: bit 3 w szumiącym bajcie →
  4/4 trafień, opóźnienie 0 ms (±0), pewność 76% ✓

## 7. Architektura (gdzie co jest)

- `canstudio/gui/server.py` — FastAPI + WS (`/api/*`, m.in. `/api/analyze/button`, `/api/pins`, `/api/insight`, `/api/uds/*`, `/api/obd/*`)
- `canstudio/gui/index.html` — cały frontend (vanilla JS, bez npm)
- `canstudio/bridging.py` — MITM + demo_virtual; `diag.py` (UDS/ISO-TP: CanStack+udsoncan+skaner), `dbcgen.py` (auto-DBC), `annotations.py` (nazwy/notatki ID), `buttonfinder.py`, `checksums.py`, `detect.py`, `markers.py`, `diffing.py`; OBD: `elm327.py` (ELM327/SPP), `obd.py` (PID/DTC/VIN + sesja), `obd_log.py` (sesje obd-logger/1)
- Sterowanie agentowe: `json_cli.py` (tryb `--json`/`--jsonl`) + `tools/ctl.py` (klient REST/WS do działającego Studia)
- Serwer MCP: `mcp_server.py` + `tools/mcp.py` (15 narzędzi `can_*`/`gui_*`, stdio; wpis w `config/mcporter.json` jako `mirican-studio`)
- Procedury: `isotp_log.py` (reassembly ISO-TP z logu) + `procedures.py` (kompilacja + magazyn `procedures/`) + `tools/proc.py`; format `mirican-procedure/1`; `docs/10-procedury.md`
- DBC: `dbc/opendbc` (58 baz), `dbc/community` (OBD2, BMW E90/E39, J1939 — MIT), `dbc/tesla_model3`, `dbc/auto_*.dbc`, `dbc/demo_gui.dbc`; profil `profiles/bmw.json` (PT-CAN 500k); loader z fallbackiem `strict=False`
- Docs: `docs/01-canable-windows.md`, `02-zasoby-dbc.md`, `03-architektura.md`, `04-mitm.md`, `05-uds.md`, `06-auto-dbc.md`, `07-annotacje.md`, `08-przeglad-kodu.md`, `09-agenci.md`, `10-procedury.md`, `11-logger.md`, `12-obd-vlinker.md`, `13-vin.md`, `14-github.md`; `README.md`, `ROADMAP.md`
- Logi: `logs/` (`gui_*.log`, `trigger_*.log`, `btn_*.log`, `uds_*.log`, `uds_scan_*.log`, `trim_*.log`); zrzuty: `design/gui-v*.png`
- Testy: `tests/test_uds_virtual.py` (UDS, 14/14), `tests/test_autodbc.py` (auto-DBC, 4/4), `tests/test_annotations.py` (anotacje, 3/3), `tests/test_logmgr.py` (logi, 3/3), `tests/test_agent_cli.py` (agentowe, 4/4), `tests/test_mcp.py` (MCP, 2/2), `tests/test_procedures.py` (procedury, 3/3)

## 8. Ostatnie sesje robocze

### 2026-10-12 — Audyt publikacji GitHub (docs/14)
- Sprawdzenie: selftest PASS, testy 62/62, pyflakes 0, smoke GUI OK (v2.4).
- Przygotowanie: `.gitignore` (can-toolkit + obd-logger), `.gitkeep` (logs/, procedures/),
  `pc/requirements.txt`; czyszczenie danych: VIN→syntetyczny (testy/docstring),
  MAC vLinkera→opcjonalny (elm327.py), ścieżki `C:\Users\...` → placeholdery
  (readme/design/docs09/handoff).
- Do decyzji: licencja (rekomendacja MIT), czy publikować handoff/roadmap, ewentualny README EN.

### 2026-10-08, v2.4 — OBD przez vLinker MS (panel GUI + szkielet loggera)
- `canstudio/elm327.py` (ELM327 po SPP/COM + auto-detekcja vLinkera) i `canstudio/obd.py`
  (PID-y/DTC/VIN; dekodery 1:1 z firmware loggera; `ObdSession` trzyma adapter + monitor).
- CLI: `py -m canstudio obd test|info|read|monitor|dtc` (+`--json`; `monitor --save` → `logs/obd_*.jsonl`).
- GUI: panel **Diagnostyka OBD** (łącze/PID-y/monitor/DTC/VIN) + szkielet zakładki **Logger OBD**
  (ustawienia `config/logger.json`, odczyt sesji + pobieranie z ESP32 po WiFi, analiza).
- `canstudio/obd_log.py` (zapis/statystyki/serie/pobieranie, kontrakt `obd-logger/1`); endpointy `/api/obd/*`.
- Testy: `test_obd_elm.py` 13/13, `test_obd_log.py` 4/4; pełna regresja 9 zestawów — zielona.
- Test na żywo (adapter podłączony): vLinker MS (COM8, ELM327 v2.3) — VIN, PID-y, DTC (2 ECU) OK.
- Pułapki: pierwsze zapytanie po ATZ trwa ~20 s (szukanie protokołu — automatyczna rozgrzewka);
  odpowiedzi z wielu ECU parsowane per linia; w PowerShell listy PID-ów w cudzysłowie.
- Poprawki po testach GUI/CLI (ten sam dzień): lista PID z zaznaczaniem + widoczny stan
  przycisku Monitor; odczyt BATCH (do 6 PID/komenda; FF/CF składane per ECU); okno odczytu
  portu 1 s → 50 ms (było ~1000 ms/komenda!); zapamiętywany protokół (`config/obd.json`) —
  kolejne połączenia ~7 s; monitor ~5× szybszy (46 odczytów/8 s); lista PID w GUI scalana
  z listą wspieranych przez auto (✓ + licznik „auto wspiera: N”; bez dekodera = odczyt surowy);
  okno OBD: 3 kolumny (PID-y | operacje | wartości), przesuwane/skalowalne z zapisem geometrii;
  przycisk „ukryj nieznane” (w okienku wartości; filtruje też listę) i feedback przycisków wyboru
  (podświetlenie stanu „wszystkie/podstawowe”, akcenty checkboxów, puls przy kliknięciu).
- Dekoder VIN: `vin.py` (WMI/rok/suma kontrolna + serie MB, silniki PSA, platformy VAG),
  CLI `vin`, endpoint `/api/obd/vin`, karta „POJAZD (z VIN)” w GUI; research: `docs/13-vin.md`
  (m.in. EU-format MB nie koduje roku — podajemy zakres lat serii). Rozszerzone (ten sam
  dzień): Toyota (poz. 8 = model), Nissan (poz. 7-9), Honda/Suzuki/Mazda/Subaru, Hyundai/Kia,
  marki chińskie (MG/BYD/Chery+Omoda/Geely/Zeekr/NIO/XPeng/GWM), ~100 WMI łącznie.

### 2026-10-07, v2.3 — Procedury F1 (ekstrakcja z nagrania)
- `proc extract <log> --pair 6F1:6F9 --save`: reassembly ISO-TP z candump (SF/FF/CF),
  parowanie tester<->ECU, kompilacja kroków (drop 3E80, pending 7F..78, timeouty x2),
  wykrywanie seed/key (pary seed→key), magazyn `procedures/*.json` (format mirican-procedure/1).
- CLI: `proc list|extract|show|rm` (+`--json`); testy `tests/test_procedures.py` 3/3.
- Konsultacja: wtyczka własna (ESP32+LCD+przyciski), pluginy procedur; plan i pytania:
  `docs/10-procedury.md` (F1 slice 1 zamknięty; następne: panel GUI + F2/F4).

### 2026-10-07, v2.2 — panel AGENT (MCP) w docku
- Opcje agenta przeniesione z zakładki Sesja do trzeciego panelu docka (była REZERWA):
  status MCP + „📋 kopiuj konfigurację” + ⟳ odświeżanie; akcent kolorystyczny zielony.

### 2026-10-07, v2.1 — serwer MCP + podłączenie agenta
- `py -m canstudio mcp`: serwer MCP (stdio, SDK `mcp` 2.x — `MCPServer`), 15 narzędzi:
  can_ports/sniff/scan/log_stats/discover/checksum/correlate/autodbc/uds/send/replay
  + gui_status/connect/frames/call (przez ctl). Zaimplementowane jako podprocesy CLI (izolacja).
- Podłączone do **mcporter**: `config/mcporter.json` → `mirican-studio` (command py + PYTHONPATH);
  `mcporter list` = healthy, 15 tools; test `mcporter call mirican-studio.can_ports` OK.
- GUI: zakładka Sesja → „AGENT (MCP)” (status + kopiuj konfigurację); endpoint `/api/mcp`.
- `requirements.txt` + `mcp>=2.0`; `tests/test_mcp.py` (2/2: rejestr + pełny handshake/tools-call po stdio).

### 2026-10-07, v2.0 — pełne wsparcie agentowe (--json/--jsonl + ctl)
- `--json`/`--jsonl` w: sniff, watch, scan, discover, correlate, checksum, stats,
  autodbc, uds, send, replay, ports; stdout czysty, tekst na stderr (`json_cli.py`).
- Nowe `py -m canstudio ctl`: klient działającego Studia (REST + WS):
  status/ports/connect/disconnect/send/frames/uds-*/log-*/replay-*/annotate/
  profiles/trigger-*/call; wyjście zawsze JSON; kody 0/2.
- `docs/09-agenci.md` + `tests/test_agent_cli.py` (4/4: sniff --jsonl na wirtualnej
  magistrali, discover --json, ctl na mini-serwerze HTTP, swap stdout/stderr).

### 2026-10-07, v1.9 — trzeci panel + naprawy łączenia
- Dock: trzeci panel **REZERWA** (pusty) + drugi separator — można zwęzić SYGNAŁY (do ~6%)
  niezależnie od reszty; `dblclick` = reset; stan w localStorage (`miriCAN_dockSplit3`).
  Test CDP: 0.45→0.06, reset OK; zrzut `design/gui-v20-three-panes.png`.
- Naprawy po zgłoszeniach:
  * `attachWS()` zamyka poprzedni socket → jeden strumień (test: 1 zamknięty + 1 żywy).
  * `connect()`: łapie brak serwera i ponawia za ~1 s; zdejmuje pauzę przy udanym połączeniu;
    `blur` przycisku.
  * SPACJA nie działa, gdy fokus na przycisku/polu (koniec przypadkowych pauz);
    pauza → toast „Podgląd wstrzymany — SPACJA wznawia”.

### 2026-10-07, v1.8 — poprawki UX (resize + DBC + lag)
- Uchwyty resize: wyraźne, zawsze widoczne paski (góra docka, separator kolumn, lewa krawędź
  prawego panelu); przeciąganie przepisane na listenery `window` (odporne na quirk pointer-capture).
  Test E2E przez CDP: kolumny 0.42→0.61, wysokość 230→290 px, dwuklik=reset — OK.
- Panel SYGNAŁY (DBC) zawsze widoczny po wyborze ID: placeholder „Nie wczytano bazy DBC…” /
  „Brak dopasowania tego ID…”; klasyfikacja: „Za mało ramek…”.
- Ostatnio wczytany DBC zapamiętywany (localStorage) i **auto-wczytywany** po odświeżeniu.
- Lag przy łączeniu: zmierzony CDP — 18 ms w czystym stanie (serwer: ramki od razu).
  Defensywnie: WS retry 1.5s→0.4s, status „ŁĄCZĘ…” po połączeniu, warm-up importów diag na starcie serwera.
- Zrzut: `design/gui-v19-handles.png`.

### 2026-10-07, v1.7 — regulacja podokien (splitters)
- Przeciągane separatory: **wysokość docka** (górna krawędź), **proporcje kolumn docka**
  (środkowy pionowy), **szerokość prawej kolumny** (lewa krawędź Inspektora);
  dwuklik = reset, stan zapamiętywany w localStorage. Hint w nagłówku docka.
- Zrzut: `design/gui-v18-splitters.png`.

### 2026-10-07, v1.6 — layout: dock analizy u dołu ekranu
- Na życzenie użytkownika: klasyfikacja bajtów + sygnały DBC przeniesione z ciastej prawej kolumny
  do poziomego panelu na dole ekranu (pełna szerokość, 2 kolumny, zwijanie ▾/▸ + localStorage).
- Prawa kolumna (Inspektor): RAMKA (z nazwą/notatką) + TRIGGER.
- Zrzut: `design/gui-v17-dock.png`.

### 2026-10-07, v1.5 — Menedżer logów + przegląd kodu
- GUI **Logi** (🗂): Statystyki (ramki/ID/czas/top z okresami), Przytnij (zakres/offset/liczba → `logs/trim_*.log`),
  Odtwarzanie z modyfikacją (drop/ustaw/licznik/suma — jak MITM; tempo/pętla/limit; potwierdzenie na realnych portach).
- CLI `replay` rozszerzony o `--set/--counter/--checksum/--drop` (silnik `bridging.transform`).
- Trigger: konfigurowalne okno −/+ [s] i tryb „ciągły” (re-arm po zapisie).
- Przegląd kodu (pyflakes + audyt): naprawiony bug duplikatu klucza `"b"` w /api/analyze/diff;
  nieużywane importy; `find_spec` w gui.py/start_menu; refaktor parserów reguł do `bridging.py`;
  raport: `docs/08-przeglad-kodu.md`.
- Testy: logmgr 3/3 (nowy), reszta bez zmian (UDS 14, auto-DBC 4, anotacje 3), pyflakes czysto.
- Zrzut: `design/gui-v16-logs.png`.

### 2026-10-07, v1.4 — anotacje ID
- **Anotacje**: nazwa + notatka dla ID, zapisywane w profilu pojazdu (`annotations` w `profiles/*.json`);
  edycja w Inspektorze (NAZWA/NOTATKA + 💾), priorytet nazw: anotacja > DBC > hex;
  wybór profilu w zakładce Sesja; `canstudio/annotations.py`; `docs/07-annotacje.md`.
  Zrzut: `design/gui-v15-annot.png`.
- API: `/api/profiles`, `/api/profile/load`, `/api/annotation`; status: `profile`, `ann`.
- Testy: anotacje 3/3 (nowy plik); reszta bez zmian.

### 2026-10-07, v1.3 — Inspektor × DBC + bazy community
- Inspektor: powiązanie klasyfikacji bajtów z sygnałami DBC (`signal_map` w `dbc.py`):
  plakietki przy bajtach, span+klasa przy sygnałach, ⚠ mieszanie klas, „poza DBC”.
  Zrzut: `design/gui-v14-link.png`.
- Bazy: `dbc/community/` — OBD2 (155 sygn.), BMW E90/E39, J1939 (MIT); nowe źródła w `docs/02-zasoby-dbc.md`.
- Loader `load_dbc` z fallbackiem `strict=False` → wczytuje się 59/67 plików (fallback odblokował
  kilkanaście baz opendbc; 8 połamanych pomijamy); lista DBC w GUI
  skanuje całe `dbc/` (rglob).
- Testy: auto-DBC 4/4 (doszedł test spanów), UDS 14/14, selftest + „biblioteka DBC”.

### 2026-10-07, v1.2 — auto-DBC + rozszerzenia panelu UDS
- Nowe: **`autodbc`** (auto-DBC z logu / `--capture`) — klasyfikacja bajtów → plik `.dbc`;
  moduł `canstudio/dbcgen.py`; dokumentacja `docs/06-auto-dbc.md`; przykłady `dbc/auto_demo_*.dbc`.
- GUI: panel Diagnostyka — **Zapis DID** i **Kasuj DTC** (checkboxy „potwierdzam”; po użyciu
  same się odznaczają); demo-ECU obsługuje zapis/odczyt F1A0.
- Fix: `selftest` — jawna flaga `is_extended_id`; odkryta pułapka python-can 4.6 (patrz sekcja 11).
- Weryfikacja: E2E GUI (zapis bez/z potwierdzeniem, odczyt zwrotny, kasowanie DTC), UDS 14/14,
  auto-DBC 3/3, selftest 8/8; zrzut `design/gui-v13-uds-write.png`.

### 2026-10-07, v1.1 — panel Diagnostyka (UDS) w GUI
- Panel **Diagnostyka** (lewa szyna, ⚙): Skanuj ECU (klik = ustaw txid) / Czytaj DID / Odczytaj DTC;
  read-only (zapis/reset tylko CLI); live trace pauzuje na czas operacji; logi `logs/uds_gui_*.log`.
- Endpointy `/api/uds/scan|read|dtc` (`asyncio.to_thread`); stany przez hash:
  `#modal=uds&udids=6F0-6FF&udrun=1&udread=1` (auto-run tylko w demo).
- Demo: wirtualny sterownik UDS (0x6F1 → 0x6F9) — pełny test panelu bez sprzętu.
- Zrzut: `design/gui-v12-uds.png`; testy CLI nadal 14/14.

### 2026-10-07, v1.0 — ISO-TP/UDS (domknięcie Etapu 1)
- Nowe: `canstudio/diag.py` (warstwa ISO-TP/UDS + skaner ECU + logi `logs/uds_*.log`)
  i komenda **`uds`**: `scan|info|read|write|dtc|session|reset|raw`; doc: `docs/05-uds.md`
- Testy: `py tests/test_uds_virtual.py` — 14/14 PASS (mock ECU na magistrali wirtualnej)
- UX: skan domyślnie 600-6FF / offset +8; NRC po nazwach; `--yes` dla zapisu/resetu/kasowania DTC;
  surowe usługi modyfikujące też wymagają `--yes`; menu START pozycje 17/18
- Zależności dodane: can-isotp 2.0.7, udsoncan 1.26.1 (w requirements.txt)

### 2026-10-07, v0.9
- Czytelność Inspektora: większe czcionki, kafelki sekcji z odcieniami, wyrównane wartości
  sygnałów (stała kolumna, prawa krawędź w pionie), legendy ＋/✓
- Sniffer v2: analiza bitowa + tło empiryczne + pewność + rozrzut opóźnienia
- Fix: link `#dbc=…` poprawnie dopasowuje plik DBC
- Testy: `node --check` OK, test bitowy OK; zrzuty `design/gui-v10-insight.png`, `gui-v11-tiles.png`

## 9. Następne kroki (kolejność)

1. ✅ ISO-TP / UDS (v1.0) — `py -m canstudio uds …`; `docs/05-uds.md`; testy 14/14
2. ✅ GUI: Diagnostyka UDS (v1.1/v1.2) — skan/DID/DTC + zapis/kasowanie za potwierdzeniem
3. ✅ Auto-DBC (v1.2) — `py -m canstudio autodbc <log>|--capture`; `docs/06-auto-dbc.md`
4. ✅ Inspektor × DBC + bazy community (v1.3) — powiązanie klasyfikacja↔sygnały;
   `dbc/community` (OBD2/BMW/J1939)
5. ✅ Anotacje ID (v1.4) — nazwy/notatki w profilu; `docs/07-annotacje.md`
6. ✅ Menedżer logów + trigger konfigurowalny (v1.5) — GUI Logi (statystyki/trim/replay z modyfikacją),
   CLI `replay --set/--counter/--checksum/--drop`; trigger −/+ i „ciągły”; `docs/08-przeglad-kodu.md`
7. Kolejne pomysły: testy HTTP (TestClient); rozbicie `gui/server.py`;
   auto-DBC z nazwami znaczników (correlate); panel „Bazy DBC” w GUI
8. **Realna sesja z autem** — czekamy na model BMW od użytkownika → dobrać DBC z `dbc/opendbc`
   + bitrate (PT-CAN 500k / K-CAN 100k), zaktualizować `profiles/bmw.json`
   (po `uds scan` dopisać znalezione pary diagnostyczne txid/rxid).
   Zasady bezpieczeństwa: najpierw sniff; TX tylko na postoju/ławce; ZAKAZ ramek airbag/hamulce/kierownica;
   termination 120 Ω OFF w aucie
9. **Skill „can-bus-mirican"** — treść przygotowana, ale `skill_workshop` blokuje tworzenie
   po stronie modelu (2× `[SKILL_WORKSHOP_EXPLICIT_INTENT_REQUIRED]`). Opcje: (a) zapis po stronie apki,
   (b) za zgodą użytkownika zapisać jako `can-toolkit/docs/09-playbook.md`. **Czeka na decyzję użytkownika.**
10. **OBD (v2.4) — dalej:** zakładka Logger OBD: synchronizacja ustawień z ESP32 / upload po WiFi
    (po bring-upie firmware); wykresy wielu PID-ów + eksport CSV; ewentualnie komenda `obdlog`
    (fetch+parse; moduł `obd_log` gotowy).

## 10. Zasady pracy (preferencje użytkownika)

- Odpowiedzi **po polsku**; nazwy funkcji po angielsku (Sniffer, Trigger, …)
- Oszczędzać kontekst: krótkie odpowiedzi, szczegóły do plików, mało zrzutów (1 na większą zmianę)
- UI: czytelność przede wszystkim, progresywne odkrywanie, maksymalna automatyzacja i prostota obsługi
- Numeracja wersji +0.1 na wydanie, wersja widoczna w UI
- Lokalny LLM (Ollama 11500) i AutoCoder — do swobodnego delegowania (trwałe zgody w MEMORY.md)

## 11. Pułapki (sprawdzone)

- Serwer pada po sleep/restarcie PC → sprawdź `http://127.0.0.1:8077/api/status`, odpal `GUI.bat`
- Stary JS w przeglądarce → F5
- „COM zajęty" → zamknij Cangaroo i inne programy; MKS reset bug → odczekaj ~2 s
- Zabijanie procesu serwera: `python.exe`/`py.exe` z „canstudio" w linii poleceń
  (`Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','py.exe') -and $_.CommandLine -match 'canstudio' }`)
- Konsola PowerShell psuje polskie znaki w podglądzie (kodowanie) — **pliki są OK (UTF-8)**;
  do czytania kodu używać narzędzia `read`
- `python` w PATH = wbudowany AutoClaw (3.13) — do projektu używać `py`
- Wydruki CLI trzymamy w cp1250: bez „→”, „●” (w pipe na Windows → `UnicodeEncodeError`); w kodzie `->`, `+`
- Loger `UdsClient` (udsoncan) wyciszony w `diag.make_client` — NRC raportujemy sami
- python-can 4.6: `can.Message(...)` ma **domyślnie `is_extended_id=True`** — zawsze podawaj
  flagę jawnie, inaczej ramka poleci jako 29-bit (dotyczy też testów!)
- Część DBC z sieci nie przechodzi cantools `strict=True` — `load_dbc` ma fallback
  `strict=False` (59/67 plików OK; 8 połamanych w opendbc pomijamy)

## 12. Start nowego czatu — wklej to

```
Kontynuujemy miriCAN Studio (CAN toolkit). Przeczytaj najpierw
<folder projektu>\can-toolkit\HANDOFF.md
i działaj dalej wg sekcji "Następne kroki". Po polsku, oszczędzaj kontekst.
```
