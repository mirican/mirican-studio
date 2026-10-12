# -*- coding: utf-8 -*-
"""Testy dekodera VIN (canstudio.vin).

Uruchomienie:
    py tests/test_vin.py
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from canstudio.vin import check_digit, decode_vin, year_candidates, year_likely  # noqa: E402

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


@test
def test_mercedes_eu():
    d = decode_vin("WDD2073221F000000")
    assert d["ok"] and d["wmi"] == "WDD", d
    assert d["brand"] == "Mercedes-Benz" and d["country"] == "Niemcy", d
    assert d["model"]["code"] == "207" and "E" in d["model"]["name"], d
    assert d["year_likely"] is None, d          # EU format MB - brak roku w VIN
    assert "Bremen" in (d.get("plant_name") or ""), d
    assert any("2009" in n for n in d["extra_notes"]), d["extra_notes"]


@test
def test_vw_platform():
    d = decode_vin("WVWZZZ1KZBW123456")
    assert d["ok"] and d["brand"] == "Volkswagen", d
    assert d["platform"]["code"] == "1K" and "Golf V" in d["platform"]["name"], d
    assert d["year_likely"] == 2011, d


@test
def test_psa_engine():
    d = decode_vin("VF3AB5FS0A0000001")
    assert d["ok"] and d["brand"] == "Peugeot", d
    assert d["engine"]["code"] == "5FS" and "THP" in d["engine"]["name"], d
    assert d["year_likely"] == 2010, d


@test
def test_year_codes():
    assert year_candidates("9") == [2009, 2039]
    assert year_likely("9") == 2009
    assert year_candidates("Y") == [2000, 2030]
    assert year_likely("Y") == 2000
    assert year_likely("T") == 2026


@test
def test_check_digit():
    vin = "1HGCM82633A004352"
    assert check_digit(vin) == "3"
    d = decode_vin(vin)
    assert d["check_digit"]["applicable"] and d["check_digit"]["valid"] is True, d
    d2 = decode_vin("1HGCM82633A004353")
    assert d2["check_digit"]["valid"] is False, d2


@test
def test_unknown_wmi_and_short():
    d = decode_vin("9BWZZZ377VT004251")
    assert d["ok"] and d["brand"] is None, d
    assert d["region"] == "Ameryka Południowa", d
    bad = decode_vin("ABC")
    assert not bad["ok"], bad


@test
def test_toyota():
    d = decode_vin("SB1KE1JE0A0000001")
    assert d["ok"] and d["brand"] == "Toyota", d
    assert d["country"] == "Wielka Brytania", d
    assert d["year_likely"] == 2010, d
    assert d["model"]["code"] == "E", d
    assert any("Toyota" in n for n in d["extra_notes"]), d["extra_notes"]


@test
def test_nissan_model_code():
    d = decode_vin("SJNFAAJ11A1234567")
    assert d["ok"] and d["brand"] == "Nissan", d
    assert d["model"]["code"] == "J11", d
    assert d["year_likely"] == 2010, d


@test
def test_chinese_brands():
    for vin, brand in (("LSJAA0A0AA0000001", "MG"),
                       ("LGXCE4CD0A0123456", "BYD"),
                       ("LVVAA0A0AA0000001", "Chery"),
                       ("L6TAA0A0AA0000001", "Geely/Zeekr")):
        d = decode_vin(vin)
        assert d.get("ok"), (vin, d)
        assert d["brand"] == brand, (vin, d)
    d = decode_vin("LSJAA0A0AA0000001")
    assert any("chińsk" in n for n in d["extra_notes"]), d["extra_notes"]


def main() -> int:
    fails = 0
    print(f"# miriCAN Studio - testy VIN ({len(TESTS)} testów)")
    for fn in TESTS:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            fails += 1
            print(f"  FAIL  {fn.__name__}: {type(exc).__name__}: {exc}")
    total = len(TESTS)
    print(f"# wynik: {total - fails}/{total} OK")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
