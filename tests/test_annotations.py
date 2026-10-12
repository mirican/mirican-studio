# -*- coding: utf-8 -*-
"""Testy anotacji ID (nazwy/notatki w profilu pojazdu).

Uruchomienie:
    py tests/test_annotations.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from canstudio.annotations import AnnotationStore, key_of, parse_key  # noqa: E402

TESTS = []
PROF = os.path.join(ROOT, "profiles", "_test_annot.json")


def test(fn):
    TESTS.append(fn)
    return fn


@test
def test_key_helpers():
    assert key_of(0x130, False) == 0x130
    assert key_of(0x18DAF110, True) == 0x18DAF110 + 0x20000000
    assert parse_key(0x130) == (0x130, False)
    assert parse_key(0x20000130) == (0x130, True)


@test
def test_roundtrip_merge():
    with open(PROF, "w", encoding="utf-8") as fh:
        json.dump({"name": "test", "bitrate": 500000}, fh)
    st = AnnotationStore(PROF)
    st.set(0x130, "DME status", "notatka testowa")
    st.set(0x20000130, "ext ramka")
    st2 = AnnotationStore(PROF)
    assert st2.name_for(0x130) == "DME status", st2.data
    assert st2.get(0x20000130)["name"] == "ext ramka", st2.data
    with open(PROF, encoding="utf-8") as fh:
        raw = json.load(fh)
    assert raw["bitrate"] == 500000, raw
    assert raw["annotations"][str(0x130)]["note"] == "notatka testowa"


@test
def test_remove_on_empty():
    st = AnnotationStore(PROF)
    st.set(0x130, "", "")
    assert st.name_for(0x130) == ""
    with open(PROF, encoding="utf-8") as fh:
        raw = json.load(fh)
    assert str(0x130) not in raw["annotations"]
    assert str(0x20000130) in raw["annotations"]


def main() -> int:
    fails = 0
    print(f"# miriCAN Studio - testy anotacji ({len(TESTS)} testów)")
    try:
        for fn in TESTS:
            try:
                fn()
                print(f"  PASS  {fn.__name__}")
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print(f"  FAIL  {fn.__name__}: {type(exc).__name__}: {exc}")
    finally:
        try:
            os.remove(PROF)
        except OSError:
            pass
    total = len(TESTS)
    print(f"# wynik: {total - fails}/{total} OK")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
