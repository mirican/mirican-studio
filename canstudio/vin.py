"""vin.py - dekoder VIN (numeru nadwozia) - zakres "co da sie ustalic".

Zakres (zweryfikowany researchem, 2026-10-08; szczegoly: docs/13-vin.md):
* uniwersalnie: WMI -> marka/kraj/region, rocznik (poz. 10, kody 30-letnie),
  suma kontrolna (norma NA), fabryka (poz. 11), numer seryjny,
* Mercedes (WDD/WDB/...): model/seria z poz. 4-6 (np. 207 -> Klasa E Coupe/Kabrio),
  orientacyjnie fabryka z poz. 11 (A-E Sindelfingen, F-H Bremen, J Rastatt),
* PSA (VF3/VF7/VR3/VR7): silnik z poz. 6-8 (kod 3-znakowy, np. 5FS, 9HZ),
* VAG (WVW/WAU/TMB/...): platforma z poz. 7-8, gdy czesc VDS to "ZZZ" (np. 1K -> Golf V),
* BMW: pozycje 4-7 to kod typu (VDS) - pelne mapowanie tylko dedykowanymi dekoderami.

Modul czysty (bez zaleznosci) - uzywa go CLI `vin`, endpoint /api/obd/vin i obd info.
"""

from __future__ import annotations

import re
import time

VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

# --- rok (poz. 10; kody powtarzaja sie co 30 lat) ---------------------------
YEAR_LETTERS = "ABCDEFGHJKLMNPRSTVWXY"  # bez I, O, Q, U, Z


def year_candidates(code: str) -> list:
    """Kandydackie roczniki dla kodu (litera: 1980+n / 2010+n; cyfra: 2000+n)."""
    code = (code or "").upper()
    if code.isdigit() and code != "0":
        d = int(code)
        return [2000 + d, 2030 + d]
    if code in YEAR_LETTERS:
        base = 1980 + YEAR_LETTERS.index(code)
        return [base, base + 30]
    return []


def year_likely(code: str) -> int | None:
    cands = year_candidates(code)
    if not cands:
        return None
    now = time.localtime().tm_year
    plausible = [y for y in cands if y <= now + 2]
    return max(plausible) if plausible else min(cands)


# --- suma kontrolna (norma NA, poz. 9) --------------------------------------
_CD_VALUES = {c: i for i, c in enumerate("0123456789")}
_CD_VALUES.update({"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7,
                   "H": 8, "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7,
                   "R": 9, "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7,
                   "Y": 8, "Z": 9})
_CD_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]


def check_digit(vin: str) -> str | None:
    if len(vin) != 17:
        return None
    total = 0
    for ch, w in zip(vin.upper(), _CD_WEIGHTS):
        v = _CD_VALUES.get(ch)
        if v is None:
            return None
        total += v * w
    rem = total % 11
    return "X" if rem == 10 else str(rem)


# --- kraje / regiony (1-2 pierwsze znaki) -----------------------------------
_REGION = {"1": "Ameryka Północna", "2": "Ameryka Północna", "3": "Ameryka Północna",
           "4": "Ameryka Północna", "5": "Ameryka Północna", "6": "Oceania",
           "7": "Oceania", "8": "Ameryka Południowa", "9": "Ameryka Południowa",
           "J": "Azja", "K": "Azja", "L": "Azja", "M": "Azja", "N": "Azja",
           "P": "Azja", "R": "Azja", "S": "Europa", "T": "Europa",
           "V": "Europa", "W": "Europa", "X": "Europa/Azja", "Y": "Europa",
           "Z": "Europa/Oceania"}
_COUNTRY2 = {"W0": "Niemcy", "WV": "Niemcy", "WA": "Niemcy", "WB": "Niemcy",
             "WD": "Niemcy", "WF": "Niemcy", "WP": "Niemcy", "W1": "Niemcy",
             "VF": "Francja", "VR": "Francja", "VS": "Hiszpania", "VX": "Francja",
             "VW": "Niemcy/Hiszpania", "UU": "Rumunia", "TJ": "Czechy?",
             "TM": "Czechy", "TS": "Węgry", "SA": "Wielka Brytania",
             "SB": "Wielka Brytania", "SH": "Wielka Brytania", "SJ": "Wielka Brytania",
             "JH": "Japonia", "JT": "Japonia", "JM": "Japonia", "JS": "Japonia",
             "JF": "Japonia", "KN": "Korea Południowa", "KM": "Korea Południowa",
             "NL": "Czechy", "U5": "Słowacja", "YV": "Szwecja", "YS": "Szwecja",
             "ZA": "Włochy", "ZC": "Włochy", "ZF": "Włochy"}

# --- WMI -> (marka, producent, kraj) ----------------------------------------
WMI = {
    # Mercedes-Benz / Daimler
    "WDD": ("Mercedes-Benz", "Mercedes-Benz Group AG", "Niemcy"),
    "WDB": ("Mercedes-Benz", "Daimler-Benz AG", "Niemcy"),
    "WDC": ("Mercedes-Benz", "DaimlerChrysler (ML/GL)", "Niemcy"),
    "WDF": ("Mercedes-Benz", "Daimler (Vito/Viano)", "Niemcy"),
    "W1K": ("Mercedes-Benz", "Mercedes-Benz AG (nowe osobowe 2019+)", "Niemcy"),
    "W1N": ("Mercedes-Benz", "Mercedes-Benz AG (SUV 2019+)", "Niemcy"),
    # BMW / Mini / Rolls
    "WBA": ("BMW", "BMW AG", "Niemcy"),
    "WBS": ("BMW M", "BMW M GmbH", "Niemcy"),
    "WBX": ("BMW", "BMW (SAV)", "Niemcy"),
    "5UX": ("BMW", "BMW (SUV, USA)", "USA"),
    "4US": ("BMW", "BMW Manufacturing (USA)", "USA"),
    "WMW": ("Mini", "BMW (Mini)", "Niemcy"),
    "SCA": ("Rolls-Royce", "Rolls-Royce Motor Cars", "Wielka Brytania"),
    # Volkswagen Group
    "WVW": ("Volkswagen", "Volkswagen AG", "Niemcy"),
    "WV1": ("Volkswagen", "VW (dostawcze)", "Niemcy"),
    "WV2": ("Volkswagen", "VW (dostawcze)", "Niemcy"),
    "3VW": ("Volkswagen", "VW de México", "Meksyk"),
    "1VW": ("Volkswagen", "VW of America", "USA"),
    "WAU": ("Audi", "Audi AG", "Niemcy"),
    "WA1": ("Audi", "Audi (SUV)", "Niemcy"),
    "TMB": ("Škoda", "Škoda Auto", "Czechy"),
    "TMP": ("Škoda", "Škoda Auto", "Czechy"),
    "VSS": ("Seat", "Seat S.A.", "Hiszpania"),
    "WP0": ("Porsche", "Porsche AG", "Niemcy"),
    "WP1": ("Porsche", "Porsche (SUV)", "Niemcy"),
    "SCB": ("Bentley", "Bentley Motors", "Wielka Brytania"),
    "ZHW": ("Lamborghini", "Automobili Lamborghini", "Włochy"),
    # PSA / Stellantis France
    "VF3": ("Peugeot", "Stellantis (PSA)", "Francja"),
    "VR3": ("Peugeot", "Stellantis (PSA)", "Francja"),
    "VF7": ("Citroën", "Stellantis (PSA)", "Francja"),
    "VR7": ("Citroën", "Stellantis (PSA)", "Francja"),
    "VF6": ("Renault", "Renault (Hiszpania)", "Hiszpania"),
    "VF1": ("Renault", "Renault SAS", "Francja"),
    "UU1": ("Dacia", "Automobile Dacia", "Rumunia"),
    # Opel / Ford
    "W0L": ("Opel", "Opel Automobile (DE/ES/PL/UK)", "Niemcy"),
    "W0V": ("Vauxhall/Opel", "Opel/Vauxhall", "Niemcy"),
    "T98": ("Opel", "Opel (dostawcze)", "Niemcy"),
    "WF0": ("Ford", "Ford-Werke GmbH", "Niemcy"),
    "WF1": ("Ford", "Ford (Europa)", "Niemcy"),
    "1FA": ("Ford", "Ford Motor Company", "USA"),
    # Włochy
    "ZFA": ("Fiat", "Fiat/Stellantis", "Włochy"),
    "ZAR": ("Alfa Romeo", "Alfa Romeo", "Włochy"),
    "ZAM": ("Maserati", "Maserati", "Włochy"),
    "ZFF": ("Ferrari", "Ferrari", "Włochy"),
    # Japonia
    "JTD": ("Toyota", "Toyota Motor", "Japonia"),
    "JTE": ("Toyota", "Toyota Motor", "Japonia"),
    "JTF": ("Toyota", "Toyota Motor (Hiace)", "Japonia"),
    "JTM": ("Toyota", "Toyota Motor", "Japonia"),
    "JTN": ("Toyota", "Toyota Motor", "Japonia"),
    "SB1": ("Toyota", "Toyota (Wielka Brytania)", "Wielka Brytania"),
    "VNK": ("Toyota", "Toyota (Francja)", "Francja"),
    "JTH": ("Lexus", "Toyota (Lexus)", "Japonia"),
    "JHM": ("Honda", "Honda Motor", "Japonia"),
    "SHS": ("Honda", "Honda (Wielka Brytania)", "Wielka Brytania"),
    "JN1": ("Nissan", "Nissan Motor", "Japonia"),
    "JN8": ("Nissan", "Nissan Motor", "Japonia"),
    "SJN": ("Nissan", "Nissan (Wielka Brytania)", "Wielka Brytania"),
    "JMZ": ("Mazda", "Mazda Motor", "Japonia"),
    "JM1": ("Mazda", "Mazda (USA)", "USA"),
    "JMB": ("Mitsubishi", "Mitsubishi Motors", "Japonia"),
    "JSA": ("Suzuki", "Suzuki Motor", "Japonia"),
    "TSM": ("Suzuki", "Magyar Suzuki", "Węgry"),
    "JF1": ("Subaru", "Subaru (FHI)", "Japonia"),
    "JF2": ("Subaru", "Subaru (FHI)", "Japonia"),
    "SAJ": ("Jaguar", "Jaguar Cars", "Wielka Brytania"),
    "SAL": ("Land Rover", "Land Rover", "Wielka Brytania"),
    # Korea / inne
    "KMH": ("Hyundai", "Hyundai Motor", "Korea Południowa"),
    "TMA": ("Hyundai", "Hyundai (Czechy)", "Czechy"),
    "KNA": ("Kia", "Kia Motors", "Korea Południowa"),
    "U5Y": ("Kia", "Kia (Słowacja)", "Słowacja"),
    "YV1": ("Volvo", "Volvo Car", "Szwecja"),
    "YV4": ("Volvo", "Volvo Car", "Szwecja"),
    "YS3": ("Saab", "Saab Automobile", "Szwecja"),
    "5YJ": ("Tesla", "Tesla Inc.", "USA"),
    "7SA": ("Tesla", "Tesla (Berlin/Chiny)", "Niemcy/Chiny"),
    "WME": ("smart", "smart (Mercedes)", "Niemcy"),
    # Japonia - dodatki
    "JN6": ("Nissan", "Nissan Motor", "Japonia"),
    "VSK": ("Nissan", "Nissan (Hiszpania)", "Hiszpania"),
    "3MZ": ("Mazda", "Mazda (Meksyk)", "Meksyk"),
    "1HG": ("Honda", "Honda (USA)", "USA"),
    "2HG": ("Honda", "Honda (Kanada)", "Kanada"),
    "3HG": ("Honda", "Honda (Meksyk)", "Meksyk"),
    "SHH": ("Honda", "Honda (Wielka Brytania)", "Wielka Brytania"),
    "4S3": ("Subaru", "Subaru (USA)", "USA"),
    "4S4": ("Subaru", "Subaru (USA)", "USA"),
    # Korea
    "KM8": ("Hyundai", "Hyundai (SUV)", "Korea Południowa"),
    "KND": ("Kia", "Kia (SUV)", "Korea Południowa"),
    # GM Korea / Chevrolet
    "KL1": ("Chevrolet", "GM Korea (Daewoo)", "Korea Południowa"),
    "KL8": ("Chevrolet", "GM Korea", "Korea Południowa"),
    # Stellantis IT / USA
    "ZLA": ("Lancia", "Lancia", "Włochy"),
    "ZCF": ("Iveco", "Iveco", "Włochy"),
    "1C4": ("Jeep/Chrysler", "Chrysler Group (Jeep)", "USA"),
    "1J4": ("Jeep", "Jeep (USA)", "USA"),
    # Chiny (top marki w PL)
    "LSJ": ("MG", "SAIC Motor (MG/Roewe)", "Chiny"),
    "LGX": ("BYD", "BYD Auto", "Chiny"),
    "LC0": ("BYD", "BYD Auto", "Chiny"),
    "LA9": ("BYD", "BYD Auto", "Chiny"),
    "LVV": ("Chery", "Chery (Omoda/Jaecoo)", "Chiny"),
    "L6T": ("Geely/Zeekr", "Geely Holding", "Chiny"),
    "LB2": ("Geely", "Geely Automobile", "Chiny"),
    "LB3": ("Geely", "Zhejiang Geely", "Chiny"),
    "LJN": ("NIO", "NIO", "Chiny"),
    "LPX": ("XPeng", "XPeng Motors", "Chiny"),
    "LGW": ("Great Wall (GWM)", "Great Wall Motor", "Chiny"),
}

# --- Mercedes: seria z poz. 4-6 + fabryka (poz. 11, orientacyjnie) ----------
MERCEDES_SERIES = {
    "117": "Klasa CLA (C117)", "118": "Klasa CLA (C118)",
    "124": "Klasa E (W124)", "140": "Klasa S (W140)",
    "156": "GLA (X156)", "163": "ML (W163)", "164": "ML (W164)",
    "166": "ML/GLE (W166)", "167": "GLE (W167)",
    "169": "Klasa A (W169)", "176": "Klasa A (W176)", "177": "Klasa A (W177)",
    "201": "190 (W201)",
    "202": "Klasa C (W202)", "203": "Klasa C (W203)",
    "204": "Klasa C (W204)", "205": "Klasa C (W205)", "206": "Klasa C (W206)",
    "207": "Klasa E Coupe/Kabrio (C207/A207)", "209": "CLK (C209)",
    "210": "Klasa E (W210)", "211": "Klasa E (W211)", "212": "Klasa E (W212)",
    "213": "Klasa E (W213)", "214": "Klasa E (W214)",
    "216": "CL (C216)",
    "218": "CLS (C218)", "219": "CLS (C219)",
    "220": "Klasa S (W220)", "221": "Klasa S (W221)", "222": "Klasa S (W222)",
    "223": "Klasa S (W223)",
    "238": "Klasa E Coupe/Kabrio (C238/A238)",
    "245": "Klasa B (W245)", "246": "Klasa B (W246)", "247": "Klasa B / GLB (W247/X247)",
    "251": "Klasa R (W251)", "253": "GLC (X253)", "254": "GLC (X254)",
    "257": "CLS (C257)", "292": "GLE Coupe (C292)",
    "447": "Vito / V-Klasse (W447)", "463": "Klasa G (W463)",
    "639": "Vito (W639)", "906": "Sprinter (W906)", "907": "Sprinter (W907)",
}
_MB_PLANTS = {"A": "Sindelfingen (DE)", "B": "Sindelfingen (DE)", "C": "Sindelfingen (DE)",
              "D": "Sindelfingen (DE)", "E": "Sindelfingen (DE)",
              "F": "Bremen (DE)", "G": "Bremen (DE)", "H": "Bremen (DE)",
              "J": "Rastatt (DE)"}

#: orientacyjne lata produkcji serii (do podpowiedzi przy braku roku w VIN)
MERCEDES_RANGES = {
    "169": "2004–2012", "176": "2012–2018", "177": "od 2018",
    "203": "2000–2007", "204": "2007–2014", "205": "2014–2021", "206": "od 2021",
    "207": "2009–2017", "211": "2002–2009", "212": "2009–2016", "213": "od 2016",
    "218": "2011–2018", "220": "1998–2005", "221": "2005–2013",
    "222": "2013–2020", "223": "od 2020", "245": "2005–2011", "246": "2011–2019",
    "247": "od 2018", "117": "2013–2019", "156": "2013–2019",
    "166": "2011–2019", "167": "od 2019", "253": "2015–2022", "254": "od 2022",
    "463": "1990–2018", "447": "od 2014", "639": "2003–2015",
}

# --- PSA: silnik z poz. 6-8 ------------------------------------------------
PSA_ENGINES = {
    "5FS": "1.6 THP (EP6DT, benzyna turbo)",
    "5FV": "1.6 THP 175 (EP6DTS, benzyna turbo)",
    "5FW": "1.6 VTi (EP6, benzyna)",
    "5FX": "1.6 THP (EP6CDT, benzyna turbo)",
    "EP6": "rodzina 1.6 THP/VTi (benzyna, PSA-BMW)",
    "9HR": "1.6 HDi/e-HDi 110-115 (DV6C, diesel)",
    "9HZ": "1.6 HDi 110 (DV6TED4, diesel)",
    "9HP": "1.6 e-HDi 115 (DV6, diesel)",
    "9HF": "1.6 HDi 92 (DV6, diesel)",
    "9HX": "1.6 HDi 90 (DV6, diesel)",
    "NFU": "1.6 16V (TU5JP4, benzyna)",
    "KFU": "1.4 (ET3, benzyna)",
    "KFV": "1.4 VTi 95 (EP3, benzyna)",
    "RFN": "2.0 16V (EW10J4, benzyna)",
    "RFJ": "2.0 16V 140 (EW10A, benzyna)",
    "RHR": "2.0 HDi 136 (DW10BTED4, diesel)",
    "DW10": "rodzina 2.0 HDi (diesel)",
}

# --- VAG: platforma z poz. 7-8 (gdy VDS zawiera "ZZZ"; orientacyjnie) -------
VAG_PLATFORMS = {
    "1K": "Golf V (Mk5) i pochodne", "5K": "Golf VI (Mk6)", "5G": "Golf VII (Mk7)",
    "1Z": "Octavia II", "5E": "Octavia III", "NX": "Octavia IV",
    "6Y": "Fabia I", "5J": "Fabia II", "NJ": "Fabia III",
    "9N": "Polo IV", "6R": "Polo V", "AW": "Polo VI",
    "1T": "Touran I", "5T": "Touran II",
    "5N": "Tiguan I", "AD": "Tiguan II",
    "3B": "Passat B5", "3C": "Passat B6", "36": "Passat B7", "3G": "Passat B8",
    "8L": "Audi A3 I", "8P": "Audi A3 II", "8V": "Audi A3 III", "8Y": "Audi A3 IV",
    "8E": "Audi A4 B6", "8K": "Audi A4 B8", "8W": "Audi A4 B9",
    "4F": "Audi A6 C6", "4G": "Audi A6 C7", "4K": "Audi A6 C8",
    "4L": "Audi Q7 I", "4M": "Audi Q7 II", "8U": "Audi Q3 I",
    "1P": "Seat Leon II", "5F": "Seat Leon III", "KL": "Seat Leon IV",
    "7M": "Sharan I", "7N": "Sharan II", "2K": "Caddy III",
    "7E": "Transporter T5", "7H": "Transporter T5",
}


def decode_vin(vin: str) -> dict:
    """Dekoduje VIN -> dict (ok/format/wmi/marka/rok/model/silnik/...)."""
    vin = (vin or "").strip().upper().replace(" ", "").replace("-", "")
    if not vin:
        return {"ok": False, "error": "Pusty VIN."}
    out: dict = {"ok": True, "vin": vin}
    if len(vin) != 17:
        out.update({"ok": False,
                    "error": f"VIN ma {len(vin)} znaków (oczekiwane 17)."})
        return out
    if not VIN_RE.match(vin):
        out["format_note"] = ("VIN zawiera niedozwolone znaki (I/O/Q) lub inne — "
                              "dekoduję ostrożnie.")

    wmi = vin[:3]
    out["wmi"] = wmi
    brand, maker, country = WMI.get(wmi, (None, None, None))
    if brand is None:
        # sprobuj po dwoch pierwszych znakach kraju
        country = _COUNTRY2.get(vin[:2])
    out["brand"] = brand
    out["manufacturer"] = maker
    out["country"] = country
    out["region"] = _REGION.get(vin[0])

    ycode = vin[9]
    out["year_code"] = ycode
    out["year_candidates"] = year_candidates(ycode)
    out["year_likely"] = year_likely(ycode)

    out["plant"] = vin[10]
    out["serial"] = vin[11:]
    out["vds"] = vin[3:9]  # 6 znakow opisowych producenta

    # suma kontrolna
    actual = vin[8]
    computed = check_digit(vin)
    applicable = vin[0] in "12345"
    cd = {"applicable": applicable, "actual": actual, "computed": computed}
    if applicable and computed is not None:
        cd["valid"] = (actual == computed)
    else:
        cd["valid"] = None
        cd["note"] = "norma północnoamerykańska; w VIN europejskich zwykle nie dotyczy"
    out["check_digit"] = cd

    notes = []

    # --- dekodery markowe ---
    if brand == "Mercedes-Benz":
        series = vin[3:6]
        if series.isdigit() and series in MERCEDES_SERIES:
            out["model"] = {"code": series, "name": MERCEDES_SERIES[series],
                            "source": "Mercedes: poz. 4-6 (Baumuster)"}
        elif series.isdigit():
            out["model"] = {"code": series,
                            "name": f"seria {series} (brak w tabeli — sprawdź w dekoderze MB)",
                            "source": "Mercedes: poz. 4-6"}
        plant = _MB_PLANTS.get(vin[10])
        if plant:
            out["plant_name"] = plant + " (orientacyjnie)"
        # europejski format MB: cyfra w poz. 10 to NIE standardowy rok
        if out["year_code"].isdigit():
            out["year_likely"] = None
            out["year_candidates"] = []
            rng = MERCEDES_RANGES.get(series)
            notes.append("Rocznik: europejski format VIN Mercedes nie używa standardowego "
                         "kodu roku (poz. 10 = „" + out["year_code"] + "”)."
                         + (f" Seria produkowana orientacyjnie: {rng}." if rng else "")
                         + " Dokładny rok: dekoder MB (mbtools/7zap) lub tabliczka znamionowa.")
        notes.append("Poz. 7-9 to wersja/odmiana wg specyfikacji Mercedesa "
                     "(nie dekodujemy uniwersalnie).")
        notes.append("Fabryka z poz. 11: zakresy liter wg dostępnych źródeł — mogą się różnić.")
    elif brand in ("Peugeot", "Citroën"):
        ecode = vin[5:8]
        fam = PSA_ENGINES.get(ecode)
        if not fam:
            fam = next((PSA_ENGINES[k] for k in PSA_ENGINES
                        if len(k) == 3 and ecode.startswith(k[:1]) and k[:2] == ecode[:2]), None)
        out["engine"] = {"code": ecode,
                         "name": fam or "nieznany w tabeli (kod 3-znakowy PSA)",
                         "source": "PSA: poz. 6-8 (kod silnika)"}
        out["model"] = {"code": vin[3:5], "name": None,
                        "source": "PSA: poz. 4-5 (model/nadwozie — pełna nazwa w dekoderze PSA)"}
        notes.append("Model/nadwozie PSA: poz. 4-5; pełne mapowanie: ServiceBox / dekodery online.")
    elif brand == "Volkswagen" or (brand in ("Audi", "Škoda", "Seat") and brand):
        code = vin[6:8]
        fam = VAG_PLATFORMS.get(code)
        if fam:
            out["platform"] = {"code": code, "name": fam, "source": "VAG: poz. 7-8 (orientacyjnie)"}
        notes.append("VAG: platforma/modele z poz. 7-8 (gdy VDS zawiera „ZZZ”) — orientacyjnie.")
    elif brand == "BMW" or brand == "BMW M":
        notes.append("BMW: poz. 4-7 to kod typu (VDS) — pełny model przez dedykowane "
                     "dekodery (mdecoder.com, bimmer.work) lub ASO.")
    elif brand in ("Opel", "Vauxhall/Opel"):
        notes.append("Opel: W0L = montaż w DE/ES/PL/UK; pełny model/silnik — dekoder online.")
    elif brand == "Ford":
        notes.append("Ford Europa: poszczególne znaki VDS zależne od modelu — dekoder online.")
    elif brand in ("Toyota", "Lexus"):
        out["model"] = {"code": vin[7], "name": None,
                        "source": "Toyota: poz. 8 = model/platforma (wg tabel Toyoty)"}
        notes.append("Toyota: poz. 8 = model/platforma wg tabel producenta (pokazujemy kod); "
                     "rok z poz. 10; fabryka — poz. 11 (0–9: Japonia wg Wikibooks). "
                     "Pełny model: toyodiy.com / partsouq.com lub ASO.")
    elif brand == "Nissan":
        out["model"] = {"code": vin[6:9], "name": None,
                        "source": "Nissan: poz. 7-9 (model wg tabel)"}
        notes.append("Nissan: model z poz. 7–9 (np. J11 = Qashqai II — wg tabel Nissana); "
                     "pełne dane: dekodery (nissanhelp / 7zap).")
    elif brand in ("Honda", "Suzuki", "Mazda", "Subaru", "Mitsubishi"):
        notes.append("Model/nadwozie/silnik wg tabel producenta (VDS) — pełny dekod: "
                     "dekodery online (7zap / partsouq).")
    elif brand in ("Hyundai", "Kia"):
        notes.append("Model/nadwozie wg VDS w tabelach Hyundaia/Kii — pełny dekod: "
                     "dekodery online (7zap / partsouq).")
    elif brand in ("MG", "BYD", "Chery", "Geely/Zeekr", "Geely", "NIO", "XPeng",
                   "Great Wall (GWM)"):
        notes.append("Marki chińskie: VIN zwykle zgodny z ISO (rok w poz. 10); pełny "
                     "model/specyfikacja: dekodery chińskich aut (chinavehiclehistory, carlytics).")
    elif brand == "Volvo":
        notes.append("Volvo: szczegóły modelu wg tabel Volvo — dekoder online.")

    if out.get("year_likely") and len(out.get("year_candidates") or []) > 1:
        notes.append("Kody rocznika powtarzają się co 30 lat — możliwe też: "
                     + ", ".join(str(y) for y in out["year_candidates"]
                                  if y != out["year_likely"]) + ".")
    out["extra_notes"] = notes
    return out
