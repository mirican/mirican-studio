"""Anotacje ID: nazwy i notatki użytkownika, zapisywane w profilu pojazdu.

Sekcja ``annotations`` w ``profiles/*.json``, klucz = ``aid`` (+``0x20000000``
dla 29-bit) — spójnie z resztą projektu. Zapis scala się z istniejącą treścią
profilu (nie nadpisuje innych pól).
"""

from __future__ import annotations

import json
from pathlib import Path

EXT_FLAG = 0x20000000


def key_of(aid: int, ext: bool) -> int:
    """Klucz globalny: aid (+ flaga 29-bit)."""
    return aid + (EXT_FLAG if ext else 0)


def parse_key(key: int) -> tuple[int, bool]:
    """Klucz -> (aid, ext)."""
    if key >= EXT_FLAG:
        return key - EXT_FLAG, True
    return key, False


class AnnotationStore:
    """Nazwy/notatki ID trzymane w pliku profilu (sekcja ``annotations``)."""

    def __init__(self, profile_path=None):
        self.path: Path | None = None
        self.data: dict = {}
        if profile_path is not None:
            self.load(profile_path)

    # ------------------------------------------------------------------
    def load(self, profile_path) -> dict:
        """Wczytuje anotacje z profilu (brak pliku = pusty zbiór)."""
        p = Path(profile_path)
        raw = {}
        if p.exists():
            with open(p, "r", encoding="utf-8") as fh:
                raw = json.load(fh) or {}
        self.path = p
        self.data = dict(raw.get("annotations") or {})
        return self.data

    def set(self, key: int, name: str = "", note: str = "") -> dict:
        """Ustawia/wpisuje anotację; pusta nazwa i notatka = usunięcie wpisu."""
        k = str(int(key))
        if not name and not note:
            self.data.pop(k, None)
        else:
            self.data[k] = {"name": str(name), "note": str(note)}
        self._save()
        return self.data.get(k, {})

    def get(self, key: int) -> dict:
        return dict(self.data.get(str(int(key))) or {})

    def name_for(self, key: int) -> str:
        return self.get(key).get("name", "")

    # ------------------------------------------------------------------
    def _save(self) -> None:
        if self.path is None:
            return
        raw: dict = {}
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh) or {}
            except Exception:  # noqa: BLE001 - uszkodzony plik: nadpisujemy sekcją
                raw = {}
        raw["annotations"] = self.data
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(raw, fh, ensure_ascii=False, indent=2)
