# 14 — Audyt: publikacja na GitHub (2026-10-12)

## 1. Wynik sprawdzenia („zrób testy”)

| Co | Wynik |
|---|---|
| selftest | **PASS** |
| testy jednostkowe | **62/62** (10 zestawów) |
| pyflakes (cały kod + testy) | **0** |
| node --check (JS GUI) | OK |
| smoke GUI | OK — v2.4, `/api/status` + `/api/obd/status` odpowiadają |

Zestawy: uds 14, autodbc 4, annotations 3, logmgr 3, agent_cli 4, mcp 2,
procedures 3, obd_elm 16, obd_log 4, vin 9.

## 2. Wyczyszczono w ramach audytu

- **`.gitignore`**: `can-toolkit/` (pycache, `logs/*`, `config/*.json`, systemowe)
  oraz `obd-logger/` (build, pycache, systemowe).
- **`.gitkeep`** w `logs/` i `procedures/` (puste foldery zostają w repo).
- **Dane osobowe usunięte z plików:**
  - prawdziwy VIN pojazdu → syntetyczny `WDD2073221F000000`
    (`tests/test_vin.py`, docstring `tools/vin.py`),
  - MAC prywatnego vLinkera → `VLINKER_MAC = ""` z opcją wpisania własnego
    (`elm327.py`; autodetekcja działa po VID Vgate / nazwie „vLinker"),
  - ścieżki użytkownika z drugiej maszyny → placeholdery `<folder projektu>`
    (readme, design/readme, docs/09-agenci, handoff).
- **`obd-logger/pc/requirements.txt`** (bleak) — kompletność instalacji.

## 3. Co zostaje poza repo (na stałe lokalnie)

- `logs/*` — 271 plików (2,1 MB; w tym sesje użytkownika po ~1 MB) — dane robocze;
- `config/*.json` — konfiguracja maszynowa (COM/protokół; wartości domyślne są w kodzie);
- `__pycache__/` oraz `obd-logger/**/build/` (~40 MB: elf/map/bin/merged.bin).

## 4. Rozmiar repo (po wykluczeniach)

- `can-toolkit` ≈ **10,4 MB**, z czego `design/` ~6,1 MB (38 PNG + mockup HTML),
  `dbc/` ~3,7 MB; kod + docs + testy < 1,5 MB;
- `obd-logger` ≈ **0,2 MB** bez `build/` (repo = kod firmware + dokumentacja;
  ~60 MB to lokalne artefakty build).

## 5. Checklista przed pierwszym push

- [x] **Licencja** — **MIT dodana** (`LICENSE` w obu repo, 2026-10-12).
      Uwaga: `dbc/opendbc/` to zewnętrzne zbiory — przed publikacją sprawdzić
      nagłówki licencyjne pojedynczych DBC (część pochodzi z projektów open source).
- [x] **`handoff.md` / `roadmap.md`** — **nie publikujemy** (zostają lokalnie; usunięte
      z indeksu git i dopisane do `.gitignore`).
- [ ] **README** — dodać przed push: sekcję „Zrzuty" (np. `design/gui-v29…`),
      wymagania (Windows, Python 3.11+), disclaimer bezpieczeństwa (praca na postoju,
      na własną odpowiedzialność), sekcję „Licencja”; opcjonalnie krótkie EN summary.
- [ ] **Nazwy repo** — propozycje: `mirican-studio` (z `can-toolkit`),
      `obd-logger` (osobne — firmware).
- [ ] Linki w `docs/11-logger.md` do `obd-logger` — przy osobnych repo podać URL GitHuba.

## 6. Pierwszy push — ✅ WYKONANO 2026-10-12

Repo publiczne: https://github.com/mirican/mirican-studio i https://github.com/mirican/obd-logger
(commity: e-mail noreply `84533131+mirican@users.noreply.github.com`; GitHub wykrywa licencję MIT).

(poniżej komendy referencyjne)

```powershell
cd <folder projektu>\can-toolkit
git init
git add .
git status                        # kontrola: brak logs/, config/, __pycache__
git commit -m "miriCAN Studio v2.4 - initial public release"
git branch -M main
git remote add origin https://github.com/<user>/mirican-studio.git
git push -u origin main
```

Analogicznie dla `obd-logger`. Przed commitem: `git ls-files` i szybki grep na
`jsonl|\.bin|\.elf|Users\\` — powinno być pusto.

**Stan maszyny: `git` zainstalowany 2026-10-12** (wersja 2.55.0.5, przez `winget`;
nowe terminale widzą `git` od razu). Przed pierwszym commitem ustaw:
`git config --global user.name "..."` i `git config --global user.email "..."`.

## 7. Ryzyka / uwagi

- Logi i config zostają lokalnie — repo nie zawiera danych z auta (0 trafień VIN w logach).
- DBC z `opendbc` — sprawdzić licencje (patrz checklista).
- Testowane na Python 3.14 / Windows 10; sugerowane minimum 3.11.
- GUI jest offline-first (`index.html` bez zależności) — dobre dla repo.
