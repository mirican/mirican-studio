# 05 — Diagnostyka UDS / ISO-TP (`canstudio uds`)

Warstwa diagnostyczna UDS na CAN: skanowanie sterowników, odczyt/zapis
identyfikatorów danych (DID), kody błędów (DTC) i sesje diagnostyczne.
To „legalna” droga do funkcji modułów, które nie są widoczne w zwykłym ruchu.

## Jak to działa

- ISO-TP: `can-isotp` 2.x (`CanStack` nad python-can) — segmentacja ramek.
- UDS: `udsoncan` 1.26 — usługi diagnostyczne (0x10, 0x22, 0x2E, 0x19, 0x14, 0x11…).
- Adresowanie: standardowe 11-bit (żądanie → odpowiedź zwykle `txid + 8`);
  opcja `--ext` dla 29-bit.
- Wszystko, co leci do/z sterownika, trafia do logu `logs/uds_*.log`
  (znaczniki `>>` wysłane / `<<` odebrane).

## Komendy

```powershell
py -m canstudio uds scan  --channel COM7                        # szukaj ECU (600-6FF, offset +8, TesterPresent 3E00)
py -m canstudio uds scan  --channel COM7 --ids "6F1,6F3" --probe 1001
py -m canstudio uds info  --channel COM7 --txid 6F1             # VIN, seria, wersje (F190, F18C, …)
py -m canstudio uds read  --channel COM7 --txid 6F1 F190 F18C F187
py -m canstudio uds dtc   --channel COM7 --txid 6F1 --session 3 # kody błędów
py -m canstudio uds dtc   --channel COM7 --txid 6F1 --clear --yes
py -m canstudio uds session --channel COM7 --txid 6F1 3
py -m canstudio uds reset --channel COM7 --txid 6F1 --type 1 --yes
py -m canstudio uds write --channel COM7 --txid 6F1 F1A0 "01 02" --yes
py -m canstudio uds raw   --channel COM7 --txid 6F1 "22 F1 90"  # surowa usługa (eksploracja)
```

Szybkie ścieżki w menu `START.bat`: **17** (scan), **18** (info).

## Panel w GUI (miriCAN Studio)

W GUI jest panel **Diagnostyka** (lewa szyna, ikona ⚙):

- **Skanuj ECU** — zakres (`600-6FF`), offset odpowiedzi, timeout; wyniki jako klikalne karty
  (klik = ustaw txid).
- **Czytaj DID** — lista DID (domyślnie F190, F18C, F187, F188, F189, F18B, F191), opcjonalna sesja.
- **Odczytaj DTC** — lista błędów ze statusami.
- **Zapis DID** / **Kasuj DTC** — wymagają zaznaczenia „potwierdzam”; reset sterownika: tylko CLI
  (`uds reset --yes`).

Na czas operacji UDS podgląd na żywo pauzuje (współdzielona magistrala); przebieg leci do
sekcji PRZEBIEG i do logu `logs/uds_gui_*.log`.

Tryb demo (`#demo=1` lub „virtual – demo”) zawiera **wirtualny sterownik UDS** (0x6F1 → 0x6F9) —
skan i odczyt DID działają bez sprzętu.

Stan przez hash (jak resztę GUI można linkować), np.:
`#demo=1&modal=uds&udids=6F0-6FF&udrun=1&udread=1` (auto-uruchomienie tylko w demo).

## Bezpieczeństwo

- **Tylko postój lub ławka** — UDS wysyła ramki; zakaz airbag/hamulce/kierownica.
- Komendy zmieniające stan (`write`, `reset`, `dtc --clear`, surowe usługi
  modyfikujące 0x11/0x14/0x27/0x2E/0x31/…) wymagają `--yes`.
- Najpierw `scan`/`sniff`, potem dopiero zapis; każda wysyłka w logu.
- Nie łącz się „na ślepo” z ID, których nie rozumiesz — najpierw ustal, który
  sterownik siedzi pod adresem (scan/info).

## Typowe DID (ISO 14229; BMW używa tych samych F1xx)

| DID | znaczenie | DID | znaczenie |
|---|---|---|---|
| F190 | VIN | F18A | identyfikator dostawcy |
| F187 | numer części/modu (HW) | F18B | data produkcji |
| F188 | numer software | F18C | numer seryjny |
| F189 | wersja software | F191 | wersja hardware |

`uds info` czyta zestaw domyślny; `--dids` nadpisuje listę.

## BMW — praktyka

- Skanuj zakres 600-6FF; typowe pary typu `0x6F1 -> 0x6F9` (offset +8).
- Bramka (ZGW) może filtrować część usług — gdy brak odpowiedzi: spróbuj
  `--probe 1001`, innego zakresu lub offsetu (linie „możliwa odpowiedź” w scan).
- K-CAN 100k vs PT-CAN 500k — ustaw bitrate: `--profile bmw` lub `--bitrate`.

## Testy bez sprzętu

```powershell
py tests/test_uds_virtual.py     # 14 testów: scan/read/write/dtc/session/reset/raw (mock ECU)
```
