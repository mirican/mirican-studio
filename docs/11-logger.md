# 11 — Logger OBD (osobny projekt): pane Guition 4.3" (P4+C6) + vLinker MS (ocena)

Projekt użytkownika (2026-10-07): osobny logger OBD — panel **Guition 4.3" (ESP32-P4 + ESP32-C6)**,
połączenie z autem przez **vLinker MS** (Bluetooth). Łańcuch:
`auto > OBD > vLinker > Bluetooth > ESP32 (P4+C6)`.

## Ocena: WYKONALNE — z jednym warunkiem do potwierdzenia (typ BT w vLinker MS)

### 1. Sprzęt P4+C6 — OK
- Guition JC-…P4 (np. JC4880P443C_I_W): P4 = UI (LVGL, MIPI-DSI 4.3", 32 MB PSRAM), **C6 = radio**
  (WiFi 6 + BT 5), spięte przez **ESP-Hosted** (C6 fabrycznie z firmware hosted 2.3.0).
- BLE central z P4 przez hosted: wspierane (HCI przez SDIO/SPI/UART; NimBLE działa „out of the box”
  wg społeczności). Uwaga: zgłaszany bug — skan BLE na P4+C6 potrafi przestać dostarczać raporty
  po ~90 s → **łączyć się po adresie/nazwie bez długiego skanu**, ewentualnie re-init; śledzić IDF 5.4+.
- P4 nie ma własnego BT/WiFi — wszystko przez C6 (to normalne dla tej pary).

### 2. vLinker MS — ROZSTRZYGNIĘTE: tryb „BT + BLE” (przełączalny) -> OK dla C6
- Ustalenia z sieci (2026-10-07): vLinker MS obsługuje **przełączane tryby połączenia**;
  wg forum Vgate, aby MS łączył się z aplikacjami po BLE, tryb zmienia się
  **z „MFI” na „BT + BLE”**; dla aplikacji iOS wymagających BT LE (4.0+) Vgate wskazuje
  **VgateFwUpdater**. Listingi potwierdzają: MS = MFi + iOS/Android/Windows, „BT 3.0”/EDR
  oraz ścieżkę BLE po zmianie trybu.
- **Wniosek:** MS da się użyć jako **BLE peripheral** — po jednorazowym przełączeniu trybu
  (VgateFwUpdater, PC/Android). Wtedy C6/P4 łączy się jako BLE central i mówi ELM327
  (ATZ, ATE0, ATSP6…, 0100…, także długie ramki — MS deklaruje do 4K bajtów żądań).
- **Test 1 (gdy MS wróci do Ciebie):** przełącz tryb na BT+BLE, potem nRF Connect →
  potwierdź usługi GATT (UUID) i połącz z PC (np. Python `bleak`) testem `ATZ`/`0100`.
- Fallbacki (gdyby coś nie grało): OBDLink CX / MX+ (jawnie BLE) albo bezpośredni CAN.
- Uwaga eksploatacyjna: BLE = **jedno połączenie naraz** (telefon zajęty → P4 się nie połączy).

### 3. Co realnie da się robić przez tę ścieżkę (oczekiwania)
- Swobodnie: PID-y OBD-II (tryb 01), DTC (03/07/0A), VIN, readiness — **datalogger parametrów**.
- Z ograniczeniami: tryby producenta (22/2E/31) przez AT + header/CAF — działa, ale wolniej i mniej pewnie.
- Ograniczone: **surowy sniff magistrali** (tylko monitor `ATMA`, straty/przepustowość) —
  do pełnego sniffu zostaje Canable / miriCAN Studio.
- Przepustowość: BLE+ELM ~20–80 ms na transakcję → praktycznie 5–20 Hz dla kilku PID-ów.
  Projektować kolejkę komend, harmonogram, retry.

### 4. Integracja z miriCAN Studio (propozycja)
- Logger zapisuje sesje jako **JSONL/CSV** (t, pid, wartość, raw) + eksport przez WiFi (HTTP/mDNS).
- W Studiu: wrzucamy pliki do `logs/` i analizujemy (agent/statystyki); opcjonalnie mini-konwerter
  `obdlog` w canstudio (później). Logi z vLinkera **nie są** surowymi ramkami CAN — to warstwa PID/ELM.
- Procedury przez vLinker: możliwe „proste” (ELM/CAF), ale nie cel loggera — do procedur mamy
  Canable + własną wtyczkę (docs/10).

### 5. Szkic architektury firmware loggera
- P4: LVGL UI + scheduler + storage (SD/FATFS) + klient WiFi do eksportu logów.
- BLE central (NimBLE przez esp-hosted) → vLinker; maszyna stanów ELM (ATZ→ATE0→ATSP6→…),
  kolejka komend, timeouty, watchdog połączenia (BLE OBD często zrywa).
- Profile pojazdów (zestawy PID per auto) + tryby: logger ciągły / trip / skan DTC / snapshot.
- Plan B (pełny sniff): dodatkowy moduł CAN (np. MCP2515 po SPI albo C3 z TWAI po UART) — inny
  produkt niż „przez vLinker”.

## Ustalenia użytkownika (2026-10-07)
- Płyta: potwierdzona (Guition 4.3" P4+C6). **Logi na SD**.
- Zakres: **ogólne OBD** (nie tylko BMW).
- **Integracja z miriCAN od razu** (format + eksport przez WiFi — do zaprojektowania).
- vLinker = wyłącznie „interface CAN” dla ESP32 (transport do magistrali; nie cel sam w sobie).

## Status
- Gotowe po naszej stronie (2026-10-07):
  * projekt `../obd-logger/` — skrypt testowy `pc/bleak_vlinker_test.py` (skan/connect/ATZ/0100;
    przetestowany: skan BLE z PC działa, vLinkera brak w pobliżu — OK),
  * kontrakt integracji `obd-logger/docs/integracja-mirican.md` (JSONL sesji PID + raw candump
    + manifest WiFi — most do Studia od pierwszego dnia).
- **Firmware: Arduino** (decyzja użytkownika, 2026-10-07): `obd-logger/arduino/miri-logger/` —
  szkielet (elm327 + obd + obdlog + BLE central) **kompiluje się** pod `esp32:esp32:esp32p4`
  (core 3.3.11; 65% flash, 0 ostrzeżeń). Wykryte wymagania: BLE przez C6 = hosted >= 2.6.0
  (update API w core); piny SDIO/SD do uzupełnienia z wiki Guition; LVGL + WiFi kolejne.
  Stary szkielet IDF: `obd-logger/firmware-idf/` (parked, referencja).
- Czekamy: (a) MS w trybie BT+BLE + test z PC (bleak); (b) płytka — bring-up (C6 fw, piny, SD).
