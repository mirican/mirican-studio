# 12 - Diagnostyka OBD-II przez adapter ELM327 (vLinker MS)

Komenda `canstudio obd` robi podstawową diagnostykę OBD-II z PC przez
adapter ELM327 (u nas: **vLinker MS** po klasycznym Bluetooth).

To osobny kanał niż CAN/Canable:

* **Canable + canstudio sniff/uds/...** = surowe ramki CAN (sniff, UDS, MITM),
* **vLinker + canstudio obd** = warstwa OBD-II (ELM327): PID-y, DTC, VIN.
  (ELM327 nie robi pełnego sniffu magistrali - do tego zostaje Canable.)

## Sprzęt / połączenie

- vLinker MS po sparowaniu z Windows pojawia się jako "Standardowy port
  szeregowy przez link Bluetooth (COMx)" - u nas **COM8**, baud **115200**.
- Port jest wykrywany automatycznie (MAC vLinkera / VID Vgate / nazwa
  "vLinker"); można też podać ręcznie: `--port COM8`.
- Wymagania: adapter włączony (zasilanie z gniazda OBD), **zapłon ON** do
  odczytów PID/DTC/VIN, telefon nie może trzymać adaptera (jedno połączenie
  naraz).
- Na PC tryb "BT+BLE" nie jest potrzebny (ten jest dla ESP32 - C6 nie ma
  klasycznego BT); klasyczne SPP działa od ręki. Docelowo vLinker MS będzie też
  interfejsem loggera ESP32 (BLE central po stronie P4/C6) - tryb "BT+BLE"
  zostaje w planie bring-upu.

## Komendy

```powershell
py -m canstudio obd test                # ATZ/ATI/ATRV + probe 0100
py -m canstudio obd info                # VIN (09 02) + wspierane PID-y
py -m canstudio obd read 010C 010D 0105 # jednorazowy odczyt
py -m canstudio obd monitor --pids 010C,010D,0105 --interval 0.3
py -m canstudio obd monitor --pids 010C,010D --save    # zapis logs/obd_<ts>.jsonl
py -m canstudio obd dtc                 # odczyt DTC (tryb 03)
py -m canstudio obd dtc --clear --yes   # kasowanie DTC (tryb 04; tylko postój)
```

Wszystkie tryby mają `--json` (monitor: `--jsonl`); stdout zostaje czysty
dla agentów (wzorzec jak w reszcie toolkitu).

## Formaty i integracja

- `monitor --save` pisze `logs/obd_<ts>.jsonl` w kontrakcie **obd-logger/1**
  (meta + rekordy `pid`) - te same pliki co logger ESP32; mogą trafić do
  dalszej analizy tym samym torem co logi Canable.
- Tabela PID i dekodery są 1:1 z firmware loggera (`obd_pids.c`) - spójne
  wartości w całym ekosystemie miriCAN.
- Warstwy: `canstudio/elm327.py` (transport AT/ELM) + `canstudio/obd.py`
  (PID-y, DTC, VIN); testy: `tests/test_obd_elm.py` (syntetyczne, bez sprzętu).

## Bezpieczeństwo

- Operacje tylko-czytające (PID-y / DTC / VIN) - bezpieczne na postoju.
- `dtc --clear` wymaga `--yes`; to jedyna komenda modyfikująca w narzędziu.
- Praca z adapterem w aucie: postój / ławka (zasady jak reszta projektu).

## Rozwiązywanie problemów

- `SEARCHING...` / `UNABLE TO CONNECT` = magistrala milczy: najczęściej
  **zapłon OFF**; sprawdź też, czy telefon nie trzyma adaptera.
- Port zajęty / brak portu: sprawdź parowanie BT (PIN 1234), ewentualnie
  usuń i sparuj ponownie; wymuś ręcznie: `py -m canstudio obd test --port COMx`.
- Pierwsze otwarcie portu BT bywa wolne (Windows "dialuje" urządzenie) -
  narzędzie ponawia próby samo. Pierwsze zapytanie po ATZ może też trwać
  ~20 s (adapter szuka protokołu w trybie ATSP0) - narzędzie robi jednorazową
  "rozgrzewkę" (0100), żeby nie ucinać szukania.
- W PowerShell listy PID-ów ujmuj w cudzysłów: `--pids "010C,0105"` (bez
  cudzysłowu przecinki tworzą tablicę, a tokeny typu `0105` bywają zamieniane
  na liczbę 105; narzędzie ma na to tolerancję, ale cytowanie jest pewniejsze).

## GUI (v2.4)

- **Panel „Diagnostyka OBD”** (lewa szyna, 🚗): Połącz / Rozłącz / Test, **lista PID-ów
  z zaznaczaniem** (wszystkie / podstawowe / wyczyść; wybór pamiętany w przeglądarce; po
  połączeniu scalana z listą wspieranych przez auto — znacznik ✓ i licznik „auto wspiera: N”;
  pozycje bez dekodera czytane surowo), odczyt „raz” i monitor na żywo (przycisk pokazuje
  stan „aktywny”; opcjonalny zapis sesji), VIN + wspierane PID-y, DTC (odczyt; kasowanie za
  checkboxem). Sesję trzyma serwer — „Rozłącz” zwalnia adapter/COM. Okno: **3 kolumny
  (wybór PID | operacje/wyniki | wartości PID)**; przesuwane za belkę i skalowalne uchwytem
  w prawym dolnym narożniku (dwuklik = reset), geometria zapamiętywana w przeglądarce.
  VIN z „VIN + wspierane” jest dekodowany — karta „POJAZD (z VIN)” (zakres: `docs/13-vin.md`).
- **Zakładka "Logger OBD"** (📊, szkielet): Ustawienia (PID-y do logowania, interwał, źródło
  PC/ESP32 - `config/logger.json`), Odczyt danych (sesje z `logs/obd_*.jsonl` + pobieranie
  z loggera ESP32 po WiFi: manifest + pliki), Analiza (statystyki per PID + wykres).
- API: `/api/obd/connect|disconnect|status|read|info|dtc|monitor/*|pids|logs|log/*|device/*`.

## Szybkość (v2.4)

- **Odczyt zbiorczy (BATCH)**: do 6 PID-ów w jednej komendzie; odpowiedzi wielo-ramkowe
  (ISO-TP FF/CF, także przeplatane z dwóch ECU) są składane per sterownik; brakujące PID-y
  dociągane pojedynczo (fallback).
- **~50 ms na komendę** (było ~1000 ms): skrócone okno odczytu portu (50 ms) zamiast
  czekania pełnej sekundy na „komplet” bufora.
- **Szybsze kolejne połączenia**: po udanym auto-search zapamiętywany jest protokół
  (`config/obd.json`) i kolejne sesje startują wprost na `ATSP<n>`; przy zmianie auta
  automatyczny fallback do pełnego szukania. Typowo: pierwsze ~15-25 s, kolejne ~3-7 s.
