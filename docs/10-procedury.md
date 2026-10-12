# 10 — Procedury: nagraj → obróbka → odtwórz w wtyczce (PROPOZYCJA — do konsultacji)

Pomysł (użytkownik, 2026-10-07): nagrać w Studiu sesję diagnostyczną wykonaną przez
komputer diagnostyczny (np. reset serwisu olejowego), przetworzyć na „mini-program”
i wgrać go do wtyczki OBD2 z ESP32+CAN, aby wtyczka **samodzielnie** wykonywała procedurę.

## Ocena wykonalności: TAK (wysoka) — większość klocków już mamy

| Element | Stan | Praca |
|---|---|---|
| Nagranie sesji (sniff + znaczniki, REC) | ✅ jest | UX „nagraj procedurę” (markery PROC-START/STOP) |
| Reassembly ISO-TP z logu (pary txid/rxid, multi-frame) | ❌ brak (live mamy) | nowy moduł `isotp_log.py` (~200 linii) |
| Kompilacja kroków (request/response, tolerancje, cleanup keepalive) | ❌ | „kompilator procedury” |
| Reguły licznik/suma (naprawa ramek przy odtwarzaniu) | ✅ `bridging.transform` | — |
| Walidacja na mock-ECU (z nagranych odpowiedzi) | ✅ wzorzec z testów | generator mocka + runner |
| Store procedur („baza”) | ❌ | `procedures/*.json` + indeks (prosto i przenośnie) |
| GUI: zakładka Procedury | ❌ | panel w Studiu (wzór: menedżer logów) |
| Firmware ESP32 (TWAI + ISO-TP + WiFi UI + flash) | ❌ | nowy podprojekt `obd-proc` |
| Upload procedur do wtyczki | ❌ | WiFi HTTP / OTA (zależnie od sprzętu) |

## Architektura (proponowana)

1. **Studio → panel „Procedury”:**
   - „⏺ Nagraj procedurę”: log z markerami; użytkownik klika procedurę na diagu; „stop”.
   - „⚙ Przetwórz”: ekstrakcja aktywnych kanałów ISO-TP z okna nagrania (typowo tester↔ECU,
     np. 0x7E0/0x7E8, BMW 0x6F1/0x6F9), reassembly, odsianie keepalive (0x3E 0x80 co ~2 s),
     deduplikacja retransmisji → **tabela kroków** (podgląd + ręczna edycja).
   - „▶ Symuluj”: mock-ECU generowany z nagranych odpowiedzi → wykonanie kroków na
     wirtualnej magistrali → raport krok-po-kroku.
   - „💾 Zapisz” → `procedures/<id>.json` (status: draft / validated / exported).
2. **Format procedury v1 (JSON)** — kroki:
   - `iso_tp` {txid, rxid, send, expect (z wildcardami `*`), timeout_ms, retries, keepalive_s}
   - `raw` {id, data, ext} — dla ramek spoza UDS
   - `wait` {ms}, `blocked` {reason} (np. seed/key), `require` (zapłon, stan)
3. **Obróbka przez agenta:** wykrycie 0x27 (seed/key) → próba wnioskowania algorytmu
   z par seed→key albo oznaczenie „wymaga klucza”; detekcja liczników/sum → reguły;
   parametryzacja; raport z nagrania. (Agent może to robić już teraz przez CLI/ctl/MCP.)
4. **Firmware `obd-proc` (ESP32 + TWAI):**
   - LittleFS + pliki procedur; WiFi AP + strona: lista, START/STOP, log;
   - wykonanie kroków z keepalive/retry, LED statusu; wybór procedury z telefonu;
   - upload procedur przez WiFi; pierwszy flash firmware przez USB/UART.
5. **MVP równoległy (bez wtyczki):** odtworzenie procedury z laptopa (`replay` + transformy)
   — dowód łańcucha, zanim powstanie firmware.

## Ryzyka i mitygacje

- **0x27 seed/key** — statyczny replay nie zadziała; wykrywamy i oznaczamy; keygen dla
  znanych marek można dopisać (moduł w Studiu/firmware).
- **Timing / P2 / S3 / keepalive** — timeouty + automatyczny 3E 80 co ~2 s w runnerze.
- **Bramka (gateway)** — nagrywamy cały ruch, więc ewentualny handshake też wpadnie do kroków.
- **Zmienność stanu ECU** — maski tolerancji, obsługa NRC (retry/abort/potwierdzenie).
- **Bezpieczeństwo** — własne auto / ławka; symulacja przed wyjazdem; ZAKAZ airbag/immobilizer
  w automacie; procedury modyfikujące tylko ze świadomą listą.
- **Sprzęt** — zależy od modelu wtyczki: czy pozwala na własny firmware i jak (USB/OTA/WiFi).

## Fazy

1. **F1**: nagrywanie + reassembly ISO-TP + kompilator + store + panel (≈1–2 sesje).
2. **F2**: mock-ECU + symulacja + raport walidacji (≈0,5 sesji).
3. **F3**: MVP na laptopie — replay procedury z Canable na aucie/ławce (część F1/F2).
4. **F4**: firmware ESP32 + upload + testy sprzętowe (≈1–2 sesje).

## Pytania do konsultacji

1. Jaka dokładnie wtyczka OBD2/ESP32 (link/model)? Jaki ma teraz firmware i jak się z nią
   łączysz (WiFi/BLE/USB)? Czy możesz wgrać własny firmware?
2. Jak wybieramy procedurę na wtyczce: telefon przez WiFi (proponuję), LED+przycisk, inne?
3. Pierwsza procedura do przeprocesowania: reset serwisu olejowego w Twoim BMW? (model/rocznik)
4. Akceptujesz format „procedures/*.json + runner + firmware”, czy wolisz surowszy replay
   ramka-po-ramce?
5. Docelowy zakres: resety serwisowe, rejestracja baterii, DPF, adaptacje? (to wpływa na
   potrzebę seed/key i złożoność)

## Ustalenia (2026-10-07, po konsultacji)

- Wtyczka: **własna konstrukcja** — ESP32 + CAN; firmware tworzymy razem.
  Sterowanie: **LCD + przyciski** (podstawowe), opcjonalnie telefon przez WiFi/BLE.
- Format: dobierany pod wykonalność; startujemy od kroków JSON (`mirican-procedure/1`)
  z możliwością oznaczania kroków wymagających wsparcia firmware (seed/key itd.).
- Zakres: **pluginy** — każda potrzebna procedura tworzona w Studiu i wgrywana do wtyczki
  w miarę potrzeby (baza `procedures/`).
- Sugestie sprzętowe (do doprecyzowania przy F4): ESP32-WROOM-32E/S3 (≥4 MB flash),
  transceiver SN65HVD230 (3.3 V) lub TJA1051T/3, zasilanie z OBD2 pin 16 (12 V -> buck),
  CAN na pinach 6/14, LCD SPI (ST7789/ILI9341) + 2-3 przyciski, obudowa z wtykiem J1962.

## Status

- **F1, slice 1 — ZROBIONE (2026-10-07, v2.3):** `canstudio/isotp_log.py` (reassembly
  ISO-TP z logu), `canstudio/procedures.py` (kompilacja + magazyn `procedures/`),
  CLI **`py -m canstudio proc`** (`list|extract|show|rm`, `--json`), testy
  `tests/test_procedures.py` (3/3; multi-frame, pending, seed/key, magazyn).
- Następne w F1: panel „Procedury” w GUI (nagraj -> przetwórz -> zapisz), potem F2
  (mock-ECU + symulacja) i F4 (firmware ESP32).
