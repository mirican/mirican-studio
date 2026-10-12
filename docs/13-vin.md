# 13 — Dekoder VIN: co da się wyciągnąć z numeru nadwozia (research)

VIN (17 znaków) rozbieramy w `canstudio/vin.py`; używa go CLI `py -m canstudio vin`,
endpoint `/api/obd/vin` i GUI (karta „POJAZD (z VIN)” po „VIN + wspierane”).

## Uniwersalna struktura (ISO 3779 / 49 CFR 565)

| Poz. | Znaczenie |
|---|---|
| 1–3 | **WMI** — producent / kraj / region (mapa w `vin.py`) |
| 4–9 | **VDS** — opis pojazdu (znaczenie zależy od marki) |
| 9 | **Suma kontrolna** — obowiązkowa w Ameryce Płn.; w Europie zwykle pomijana |
| 10 | **Rok modelowy** — cykl 30-letni; litery bez I/O/Q/U/Z (A=1980/2010, L=1990/2020, Y=2000/2030; cyfry 1–9 = 2001–2009/2031–2039) |
| 11 | **Fabryka/zakład** (znaczenie zależy od marki) |
| 12–17 | Numer kolejny (seryjny) |

Uwaga: kody roku powtarzają się co 30 lat — z samego VIN rok jest niejednoznaczny
(narzędzie pokazuje kandydatów i wybiera najbardziej prawdopodobny).

## Co dekodujemy per marka (stan: v2.4)

| Marka | Co da się ustalić z VIN | Uwagi |
|---|---|---|
| **Mercedes-Benz** (WDD/WDB/WDC/WDF/W1K/W1N) | seria/model z poz. 4–6 (207 → Klasa E Coupe/Kabrio C207/A207; 204 → C; 212 → E…); fabryka z poz. 11 (A–E Sindelfingen, F–H Bremen, J Rastatt — orientacyjnie) | **Europejski format nie koduje roku w poz. 10** (cyfra, np. „1”); rocznik: dekoder MB (mbtools/7zap) lub tabliczka. Auta na USA (np. WDD… z literą roku) mają rok w poz. 10 |
| **BMW** (WBA/WBS/WBX/5UX/4US) | marka, rok (poz. 10), fabryka; poz. 4–8 = VDS („kod typu”) | Pełny model (np. F30 320d) tylko dedykowanym dekoderem: mdecoder.com, bimmer.work. Od ~2019 BMW recyklinguje ostatnie 7 znaków — unikalny jest cały VIN |
| **VAG** (WVW/WAU/TMB/VSS/WP0…) | rok (poz. 10); **platforma z poz. 7–8** gdy VDS = „ZZZ”: 1K→Golf V, 5K→Golf VI, 5G→Golf VII, 5E→Octavia III, 5F→Leon III, 8V→A3 III, 8W→A4 B9, 4G→A6 C7 itd.; fabryka poz. 11 (litery zakładów) | Platformy orientacyjnie; auta USA: dodatkowo silnik z poz. 5 |
| **PSA: Peugeot/Citroën** (VF3/VR3/VF7/VR7) | poz. 4 = linia modelowa, poz. 5 = nadwozie, **poz. 6–8 = kod silnika** (3-znakowy): 5FS=1.6 THP (EP6), 5FW=1.6 VTi, 9HZ/9HR/9HP=1.6 HDi (DV6), NFU=1.6 16V, RFN/RFJ=2.0, RHR=2.0 HDi… | Format 2009+; starsze roczniki inaczej. Pełny model: ServiceBox/dekodery |
| **Opel/Vauxhall** (W0L, T98) | marka/kraj (W0L = montaż DE/ES/PL/UK) | Model/silnik z VIN tylko przez dekoder online |
| **Ford** (WF0/WF1 Europa) | marka/kraj | Poz. 4–7 zależne od modelu; dekoder online |
| **Renault/Dacia** (VF1/VF6/UU1) | marka/kraj | „Typ mine” poza VIN (tabliczka); dekoder online |
| **Toyota/Lexus** (JTD/JTE/JTF/JTM/JTN/SB1/VNK/JTH) | marka/kraj, rok (poz. 10), fabryka (poz. 11; 0–9 = Japonia wg Wikibooks), **poz. 8 = model/platforma** (wg tabel Toyoty — pokazujemy kod) | Pełny model (np. Corolla E210): toyodiy.com / partsouq / ASO |
| **Hyundai/Kia** (KMH/TMA/KNA/U5Y) | marka/kraj, rok, fabryka | VDS wg tabel producenta |
| **Nissan** (JN1/JN6/JN8/SJN/VSK) | marka/kraj, rok, fabryka; **poz. 7–9 = model** (np. J11 = Qashqai II) | Pełne dane: nissanhelp / 7zap |
| **Honda / Suzuki / Mazda / Subaru / Mitsubishi** | marka/kraj, rok, fabryka; model wg tabel (VDS) | Dekodery online (7zap / partsouq) |
| **Volvo** (YV1/YV4) | marka/kraj, rok | Model wg tabel Volvo — dekoder online |
| **Marki chińskie**: MG (LSJ), BYD (LGX/LC0/LA9), Chery/Omoda/Jaecoo (LVV), Geely/Zeekr (L6T/LB2/LB3), NIO (LJN), XPeng (LPX), GWM (LGW) | marka/kraj; VIN zwykle wg ISO (rok w poz. 10) | Pełny model: chinavehiclehistory / carlytics |
| **Jeep/Chrysler** (1C4/1J4), **smart** (WME), **Lancia** (ZLA), **Iveco** (ZCF), **Chevrolet** (KL1/KL8) | marka/kraj, rok | Model: dekoder online |
| **Stellantis IT** (ZFA/ZAR/ZAM/ZFF) | marka (Fiat/Alfa/Maserati/Ferrari), rok | Model: dekoder online |
| **Tesla** (5YJ) | marka, rok; VDS zawiera model/baterię | |

W tabelach w `vin.py` mamy ~100 WMI (UE, Japonia, Korea, Chiny, USA), serie
Mercedesa (~45), kody silników PSA, platformy VAG oraz kody roku i algorytm sumy
kontrolnej (norma NA).

## Dekodery online (do pełnych danych: opcje, silnik, wersja)

- **Mercedes**: mbtools.com/vin, 7zap.com, lastvin.com
- **BMW**: mdecoder.com, bimmer.work (po ostatnich 7 znakach; pełny VIN od 2019)
- **PSA**: ServiceBox (warsztat) / dekodery typu vindecoder.eu
- **Ogólne**: vindecoder.eu, carlytics.eu, listocar.com, epicvin.com
- **USA/NA**: NHTSA vPIC (vpic.nhtsa.dot.gov) — pełny dekoder rządowy

## Źródła researchu (2026-10-08)

- Wikibooks — *Vehicle Identification Numbers (VIN codes)*: sekcje Mercedes-Benz
  (formats: „European/World market cars use a different system”), Peugeot
  („Engine (position 6)”), Check digit, Model year
- carlytics.eu — Mercedes/Peugeot/Ford: pozycje 4–6 MB (204=W204, 212=W212);
  Peugeot: poz. 4 model, 5 nadwozie, 6+ silnik
- aussiefrogs.com + autoparts-24.com — PSA: „positions 6–8 carry the 3-character
  [engine] short code” (5FS, 9HZ…)
- clubvw.org.au + „VW VIN Decoder 2007” — VAG: poz. 7–8 = model code
- mbofnorthscottsdale.com / dealerfire / listocar — MB: poz. 10 rok (USA),
  poz. 11 fabryka (A–E Sindelfingen, F–H Bremen)
- alldata.com / faxvin.com — tabela kodów roku (poz. 10)
- red-headed.com / autolawfirm.com / 49 CFR 565 — algorytm sumy kontrolnej
- autopartex.io / vinwiser.com — Opel W0L
- bmwblog.com / f30.bimmerpost.com — BMW VDS i recykling końcówek VIN (2019+)
- carpeep.co.uk + carlytics.eu — Nissan: WMI (SJN/JN1/JN8/JN6/VSK), model z poz. 7–9
- wikibooks — Nissan (format EU), Toyota (poz. 8 model/platforma, poz. 11 fabryka)
- chinavehiclehistory.com + softechpro-solutions.com — WMI chińskich marek
  (LGX/LC0=BYD, LSJ=MG/SAIC, LVV=Chery, L6T/LB2/LB3=Geely, LJN=NIO, LPX=XPeng)

## Ograniczenia

- Z samego VIN **nie** odczytasz: przebiegu, historii, wersji wyposażenia, mocy
  silnika dla większości marek (to wymaga baz producenta / raportów).
- Kody roku są 30-letnie (niejednoznaczne); auta europejskie często nie używają
  sumy kontrolnej; Mercedes EU nie koduje roku w standardowym miejscu.
- Mapowania „platforma VAG” i „serie MB” podane orientacyjnie — do weryfikacji
  w dekoderach producenta przy wątpliwościach.
