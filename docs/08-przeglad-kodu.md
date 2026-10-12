# 08 — Przegląd kodu i refaktoryzacja (2026-10-07)

Przegląd wykonany na wersji v1.5 (po Menedżerze logów). Zakres: `canstudio/`, `tests/`,
`start_menu.py`; narzędzia: `pyflakes`, testy syntetyczne, audyt ręczny.

## Metryki

- Kod Python: ~40 plików; największy moduł: `gui/server.py` (≈1,5 tys. linii — CanManager + REST + WS).
- Testy: 5 zestawów syntetycznych — UDS 14/14, auto-DBC 4/4, anotacje 3/3, logmgr 3/3,
  plus `selftest` (9 pozycji, w tym biblioteka DBC i sprzęt opcjonalnie).
- Frontend: `index.html` ~2 tys. linii (vanilla JS, zero npm).
- pyflakes: **czysto (0 ostrzeżeń)** po poprawkach.

## Ocena budowy (mocne strony)

- Modularny pakiet z rejestrem narzędzi (`tools/__init__.py`) — nowe komendy dodaje się lokalnie;
  CLI i GUI korzystają z tych samych modułów (`bus`, `logio`, `bridging`, `diag`, `dbcgen`, `annotations`).
- Jedno źródło prawdy dla reguł modyfikacji: `bridging.py` (bridge + replay + GUI).
- Warstwa DBC spójna (cantools + fallback `strict=False`); mapowanie sygnał↔bajty przetestowane.
- Bezpieczeństwo: `--yes` / checkboxy potwierdzeń, log każdej wysyłki, silent-mode domyślnie w watch/scan.
- Testy bez sprzętu (magistrale wirtualne) → szybka regresja po każdej zmianie.

## Znalezione i naprawione (v1.5)

1. **Bug: duplikat klucza `"b"` w `/api/analyze/diff`** — indeks bajtu był nadpisywany listą
   wartości; etykiety w panelu Diff pokazywały śmieci („b12,13,14"). Naprawione: pole `byte`
   (+ frontend).
2. Nieużywane importy: `ClientConfig` (`diag.py`), `Optional` (`diffing.py`), `math`
   (`server.py`, pozostałość w `_start_demo`).
3. `tools/gui.py` i `start_menu.py`: sprawdzanie zależności przez import → `importlib.util.find_spec`
   (czystsze, bez „fałszywych" importów).
4. `trim_messages`: tolerancja float (epsilon) — granice zakresu nie gubią skrajnych ramek.
5. **Limit 60 plików w `/api/logs`** — przy 141 logach starsze (np. `demo_b.log`) wypadały
   z listy i nie dało się ich wybrać w GUI. Podniesione do 200; weryfikacja E2E (zrzut).
6. Wcześniej w tym cyklu prac: python-can 4.6 `is_extended_id=True` (domyślne!) — audyt + fix
   w selftest; wyciszenie logera `UdsClient`; wydruki CLI bezpieczne dla cp1250.

## Refaktoryzacje (v1.5)

- Parsery specyfikacji reguł (`ID:BYTE=VALUE`, `ID:BYTE`, `ID:BYTE:ALGO`) przeniesione
  z `tools/bridge.py` do `bridging.py` (`parse_set_spec`, `parse_counter_spec`,
  `parse_checksum_spec`) — wspólne dla bridge i replay.
- GUI: `collectRules` uogólnione do `collectRulesFrom(...)` — MITM i Menedżer logów dzielą kod.
- Menedżer logów zbudowany na istniejących klockach: `logio.trim_messages` +
  `bridging.transform` + `IdStats` (zero duplikacji silników).

## Słabe punkty / rekomendacje na później

- `gui/server.py` rośnie. Przy kolejnych funkcjach warto wydzielić: `gui/manager.py`
  (CanManager), `gui/logmgr.py`, `gui/uds_api.py`. Najpierw jednak testy warstwy HTTP.
- Brak automatycznych testów HTTP (poza ręcznym E2E). Kandydat: `tests/test_server_api.py`
  z FastAPI `TestClient` na wirtualnej magistrali.
- Cache listy DBC w GUI (obecnie rglob przy każdym otwarciu; drobiazg przy ~67 plikach).
- Gdy `index.html` przekroczy ~3 tys. linii — rozbić na `app.js` + `styles.css`
  (serwer trzeba wtedy rozszerzyć o serwowanie statyków).

## Wniosek

Stan dobry: spójna architektura, 24 testy syntetyczne + selftest, pyflakes czysty.
Główne ryzyko: rosnący `server.py` i brak testów HTTP — zaplanowane powyżej.
