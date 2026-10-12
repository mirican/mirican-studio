"""Konfiguracja projektu: ścieżki, profile pojazdów, wartości domyślne."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # katalog can-toolkit/
PROFILES_DIR = ROOT / "profiles"
LOGS_DIR = ROOT / "logs"
DEFAULT_BITRATE = 500000


def resolve_path(p):
    """Ścieżka względna -> bezwzględna (względem katalogu projektu)."""
    if not p:
        return None
    path = Path(p)
    return path if path.is_absolute() else (ROOT / path)


def load_profile(name: str) -> dict:
    """Ładuje profil pojazdu z profiles/ (nazwa lub ścieżka)."""
    p = Path(name)
    if not p.suffix:
        p = PROFILES_DIR / (name + ".json")
    elif not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        raise SystemExit(f"Nie znaleziono profilu: {name} (szukano: {p})")
    with open(p, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("name", p.stem)
    return data


def list_profiles():
    """Nazwy dostępnych profili."""
    if not PROFILES_DIR.exists():
        return []
    return sorted(p.stem for p in PROFILES_DIR.glob("*.json"))


def resolve_args(args) -> None:
    """Uzupełnia wartości domyślne na podstawie --profile (i globalnych)."""
    profile = None
    name = getattr(args, "profile", None)
    if name:
        profile = load_profile(name)
        args._profile = profile

    if getattr(args, "bitrate", None) is None:
        args.bitrate = (profile or {}).get("bitrate") or DEFAULT_BITRATE

    if hasattr(args, "dbc") and not getattr(args, "dbc", None) and profile and profile.get("dbc"):
        args.dbc = str(resolve_path(profile["dbc"]))

    if hasattr(args, "log_dir") and not getattr(args, "log_dir", None):
        args.log_dir = str(LOGS_DIR)
