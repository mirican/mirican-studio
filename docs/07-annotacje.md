# 07 — Anotacje ID (nazwy i notatki w profilu pojazdu)

Kliknij ramkę w Live Trace → w Inspektorze, w karcie **RAMKA**, ustaw
**NAZWĘ** i **NOTATKĘ** → „💾 zapisz". Wpis ląduje w profilu pojazdu
(`profiles/*.json`, sekcja `annotations`) i od tej chwili:

- nazwa pojawia się w kolumnie NAZWA w Live Trace (priorytet: anotacja > DBC > hex),
- filtr w Live Trace działa też po tej nazwie,
- notatka czeka w Inspektorze przy wyborze ramki.

## Profile

- Zakładka **Sesja** → „PROFIL / ANOTACJE": lista profili z liczbą anotacji,
  „wczytaj" przełącza aktywny profil, ⟳ odświeża listę.
- Domyślnie aktywny: `profiles/bmw.json`.
- API: `GET /api/profiles`, `POST /api/profile/load {name}`, `POST /api/annotation {key,name,note}`.
- Klucz anotacji: `aid` (+`0x20000000` dla 29-bit) — spójny z resztą projektu
  (`canstudio.annotations.key_of`).
- Pusta nazwa i notatka = usunięcie wpisu.

## Uwagi

- Zapis scala się z profilem — pozostałe pola (bitrate, dbc, notes…) zostają.
- Anotacje nie zależą od DBC: działają też bez wczytanej bazy.
- Po zmianie profilu nowe ramki od razu dostają nowe nazwy.
