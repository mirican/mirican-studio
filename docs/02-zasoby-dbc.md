# Zasoby: bazy CAN (DBC), narzędzia, społeczność

> Stan na 2026-10-05. Część baz mamy lokalnie w `dbc/`.

## 1. Lokalnie (w tym repo)

* `dbc/opendbc/` — **58 plików DBC** z https://github.com/commaai/opendbc (licencja MIT):
  VW (MQB, MQB Evo, MLB, PQ), BMW E9x/E8x, Mercedes E350, Tesla (can/model3/powertrain),
  Toyota (2017/prius/iQ/ADAS/TSS2), Ford + FORD CADS, Lincoln, GM Global A + Cadillac CT6,
  Hyundai/Kia (ccan/mcan/i30/Santa Fe), Nissan Xterra, Mazda (2017/Mazda3/RX-8),
  PSA, Opel, Volvo, Chrysler/Pacifica, FCA Giorgio, Acura, BYD, GWM, Hongqi, Luxgen, MG,
  Rivian, radar ESR.
* `dbc/tesla_model3/Model3CAN.dbc` — https://github.com/joshwardell/model3dbc
* `dbc/community/` (2026-10-07) — ręcznie wybrane, licencje **MIT**: **OBD2** (155 sygnałów),
  **BMW E90** (66 wiad.), **BMW E39**, **J1939** (podstawowe PGN) — patrz `dbc/community/README.md`

## 2. Główne źródła baz (multi-marka)

* **commaai/opendbc** — https://github.com/commaai/opendbc — największa otwarta
  kolekcja DBC (300+ modeli w openpilot). `git clone --depth 1` i masz całość.
  Metodyka portowania aut: sekcja *How to Port a Car* w README.
* **commaCarSegments** — https://huggingface.co/datasets/commaai/commaCarSegments —
  surowe logi CAN z ~300 modeli (do korelacji/walidacji).
* **GitHub topics** — https://github.com/topics/dbc , https://github.com/topics/can-bus
* **nberlette/canbus** — https://github.com/nberlette/canbus — OBD2 + BMW (E39/E90) + wiki (MIT)
* **nberlette/bmw-dbc** — https://github.com/nberlette/bmw-dbc — BMW E90/E39 (MIT)
* **J1939-DBC-Database** — https://github.com/arthithadee/J1939-DBC-Database — PGN J1939 (MIT)
* **awesome-automotive-can-id** — https://github.com/iDoka/awesome-automotive-can-id — lista źródeł per marka
* **SavvyCAN discussions** — https://github.com/collin80/SavvyCAN/discussions/798 — wątki o DBC per auto
* Wyszukiwanie: https://github.com/search?q=%22dbc%22+<marka>&type=repositories
  (np. „tesla dbc", „bmw dbc", „vag dbc").

## 3. Per producent (poza opendbc)

### VAG (VW/Audi/Škoda/Seat)
* opendbc: `vw_mqb`, `vw_mqbevo`, `vw_mlb`, `vw_pq`
* Ross-Tech wiki (VCDS; kody błędów, opisy bloków) — https://wiki.ross-tech.com
* Fora: vwvortex.com, motor-talk.de

### BMW
* opendbc: `bmw_e9x_e8x.dbc`
* ekosystem diagnostyczny: INPA / EDIABAS / NCS Expert (fora: bimmerfest, bmwcoders);
  GitHub search: `BMW dbc`

### Mercedes
* opendbc: `mercedes_benz_e350_2010.dbc`; GitHub search: `mercedes can dbc`

### GM / Cadillac
* opendbc: `gm_global_a_*` (powertrain/chassis/object/low speed), `cadillac_ct6_*`

### Ford / Lincoln
* opendbc: `ford_*` (CGEA 1.2 body/pt, Fusion 2018, Lincoln), `FORD_CADS*`
* FORScan (darmowa diagnostyka Ford) — https://forscan.org

### FCA / PSA / Opel / Renault
* opendbc: `chrysler_*`, `fca_giorgio`, `psa_aee2010_r3`, `opel_omega_2001`
* Renault/Dacia: **ddt4all** — https://github.com/cedricp/ddt4all (bazy DDT2000)

### Toyota / Lexus
* opendbc: `toyota_2017_ref_pt`, `toyota_prius_2010_pt`, `toyota_iQ_2009`,
  `toyota_adas`, `toyota_tss2_adas`, radar DSU

### Nissan / Leaf (EV)
* opendbc: `nissan_xterra_2011`
* Leaf: https://github.com/lincomatic/LeafCAN ,
  https://github.com/sethfischer/nissan-leaf-obd-manual ,
  https://github.com/macleod-matt/nissan-leaf-can-bms
* EV ogólnie: https://openinverter.org/forum (mapy baterii i napędów EV),
  OVMS — https://github.com/openvehicles/Open-Vehicle-Monitoring-System-3

### Tesla
* opendbc: `tesla_can`, `tesla_model3_party`, `tesla_model3_vehicle`, `tesla_powertrain`
* https://github.com/joshwardell/model3dbc (Model3CAN.dbc)
* community: forum TMC, wątki użytkownika wk057; projekt OVMS

### Hyundai / Kia / Genesis
* opendbc: `hyundai_2015_ccan/mcan`, `hyundai_i30_2014`, `hyundai_santafe_2007`

### Mazda / Subaru / Honda / Volvo i pozostałe
* opendbc: `mazda_*`, `volvo_*`, `acura_*`
* pozostałe marki: GitHub search + awesome-canbus (niżej)

## 4. Narzędzia

* **Cangaroo** — https://github.com/HubertD/cangaroo — GUI Windows/Linux,
  obsługuje slcan + candleLight, wysyłka, DBC („pierwszy wybór" na Windows).
* **SavvyCAN** — https://github.com/collin80/SavvyCAN — analiza nagrań,
  wykresy, DBC; importuje m.in. ASC/BLF/TRC/candump.
* **CAN++** — https://github.com/TDahlmann/canpp — Windows, symboliczne
  nazwy z DBC, wykresy.
* **cabana** — https://github.com/commaai/cabana — wizualne rozgryzanie CAN.
* **cantools** — https://github.com/cantools/cantools — Python + CLI; używamy w naszych skryptach.
  Przykłady: `py -m cantools dump plik.dbc` oraz dekodowanie logu (dekoder czyta
  ramki „candump" ze standardowego wejścia):
  `Get-Content logs\dump.log | py -m cantools decode dbc\opendbc\vw_mqb.dbc`
* **canmatrix** — https://github.com/ebroecker/canmatrix — konwersje DBC↔ARXML/KCD.
* **Caring Caribou** — https://github.com/CaringCaribou/caringcaribou — skaner UDS.
* **python-udsoncan** — https://github.com/pylessard/python-udsoncan ,
  **python-can-isotp** — https://github.com/pylessard/python-can-isotp — diagnostyka UDS/ISO-TP.
* **can-utils** (Linux) — https://github.com/linux-can/can-utils (candump…).

## 5. Wiedza / metodyka

* **The Car Hacker's Handbook** (Craig Smith; darmowy PDF) — https://opengarages.org/handbook
* **CSS Electronics** — wprowadzenia do CAN i DBC:
  https://www.csselectronics.com/pages/can-bus-simple-intro-tutorial ,
  https://www.csselectronics.com/screen/page/can-dbc-file-database-intro/language/en
* **awesome-canbus** — https://github.com/iDoka/awesome-canbus — katalog
  narzędzi (sekcje: hacking, DBC, hardware, protokoły).
* **OBD-II PIDs** — https://en.wikipedia.org/wiki/OBD-II_PIDs
* Reddit: https://reddit.com/r/CANbus

## 6. Jak rozgryzać nowe auto (skrót)

1. Ustal magistralę i prędkość (typowo OBD-II: pin 6=CAN-H, 14=CAN-L, 500k;
   magistrale „komfort" bywają 125k/250k na innych pinach — patrz dokumentacja auta).
2. Nasłuchuj pasywnie: `py sniff.py -c COM7` — poklikaj, pojeźdź na postoju,
   włączaj/wyłączaj funkcje; zapis w `logs/`.
3. Analizuj: ramki cykliczne = wskaźniki (prędkość, obroty); skoki przy akcji =
   kandydaci na komendy.
4. Sprawdź, czy model jest blisko któregoś DBC z `dbc/opendbc` — uruchom sniff
   z `--dbc` i patrz na nazwy sygnałów.
5. Buduj własny DBC (cabana / CAN++ / SavvyCAN) i dokładaj sygnały.
6. Dopiero potem wysyłka / replay — świadomie i w kontrolowanych warunkach.
