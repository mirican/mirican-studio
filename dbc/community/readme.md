# dbc/community — ręcznie wybrane bazy DBC (stan 2026-10-07)

Pliki pobrane z otwartych źródeł, wszystkie o licencji **MIT** (zweryfikowane
przez GitHub API w dniu pobrania).

| plik | źródło | licencja | zawartość |
|---|---|---|---|
| `nberlette_canbus/OBD2.dbc` | github.com/nberlette/canbus | MIT | OBD-II standard — 155 sygnałów (PID) |
| `nberlette_canbus/bmw-e90.dbc` | github.com/nberlette/canbus | MIT | BMW E90 — 66 wiadomości |
| `nberlette_canbus/bmw-e39.dbc` | github.com/nberlette/canbus | MIT | BMW E39 — 3 wiadomości |
| `j1939/j1939_database.dbc` | github.com/arthithadee/J1939-DBC-Database | MIT | J1939 — podstawowe PGN (8 wiadomości) |

## Sprawdzone, ale nie kopiowane (linki)

- **joshwardell/model3dbc** (MIT) — Model3CAN.dbc; mamy już identyczny plik
  w `dbc/tesla_model3/`.
- **autti/abraham** (MIT) — lincoln_mkz.dbc; Lincoln jest szerzej pokryty
  w opendbc (`ford_lincoln_base_pt.dbc`).

## Uwagi

- Loader `canstudio.dbc.load_dbc` ma fallback `strict=False` — część baz
  z sieci nie przechodzi ścisłej walidacji cantools i wczytuje się luźno
  (dzięki temu działa 59/67 plików w całym `dbc/`).
- `dbc/opendbc/` bez zmian (58 baz, komplet wg stanu repo).
