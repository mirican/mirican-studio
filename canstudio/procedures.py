"""Procedury („mini-programy”): kompilacja kroków i magazyn ``procedures/``.

Format: ``mirican-procedure/1`` — JSON z krokami wykonywalnymi przez runner
(Studio: symulacja/replay; wtyczka ESP32: standalone).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .config import ROOT

PROC_DIR = ROOT / "procedures"
FORMAT = "mirican-procedure/1"

_SLUG = re.compile(r"[^a-z0-9]+")


def hexs(data: bytes | None) -> str:
    return " ".join(f"{b:02X}" for b in data) if data else ""


def slug(text: str) -> str:
    s = _SLUG.sub("_", str(text).strip().lower()).strip("_")
    return s or "procedura"


def compile_procedure(session, name: str, vehicle: str = "",
                      source_log: str = "", drop_keepalive: bool = True) -> dict:
    """Sesja ISO-TP → procedura (lista kroków) wg formatu v1."""
    sec_pairs = []
    seed_req = None
    steps = []
    for ex in session.exchanges:
        req = ex.req
        if not req:
            continue
        sid = req[0]
        if drop_keepalive and sid == 0x3E:  # TesterPresent — runner doda sam
            continue
        if sid == 0x27 and len(req) >= 2:  # SecurityAccess — księgujemy pary
            odd = (req[1] % 2) == 1  # requestSeed
            if odd and ex.resp is not None and ex.resp[:1] == b"\x67":
                seed_req = ex.resp[2:]
            elif not odd and seed_req is not None:
                sec_pairs.append({"seed": hexs(seed_req), "key": hexs(req[2:])})
                seed_req = None
        timeout_ms = 1500
        if ex.resp_t is not None and ex.resp_t > ex.t:
            timeout_ms = max(200, int((ex.resp_t - ex.t) * 1000 * 2))
        step = {
            "op": "iso_tp",
            "txid": f"0x{session.req_id:X}",
            "rxid": f"0x{session.resp_id:X}",
            "send": hexs(req),
            "expect": hexs(ex.resp) if ex.resp is not None else None,
            "timeout_ms": timeout_ms,
        }
        if ex.pendings:
            step["pendings"] = ex.pendings
        if sid == 0x27:
            step["note"] = ("security access — wymaga algorytmu klucza; "
                            "nie odtworzy się jako statyczny replay")
        steps.append(step)
    proc = {
        "format": FORMAT,
        "id": slug(name),
        "name": name,
        "vehicle": vehicle,
        "created": datetime.now().isoformat(timespec="seconds"),
        "source": {"log": source_log},
        "transport": {"bitrate": None, "ext": session.ext},
        "security": {"detected": bool(sec_pairs), "pairs": sec_pairs},
        "steps": steps,
        "notes": "",
    }
    if sec_pairs:
        proc["security"]["note"] = ("zebrano pary seed→key — kandydat do analizy "
                                    "algorytmu klucza przed użyciem standalone")
    return proc


# ---------------------------------------------------------------------------
# Magazyn („baza procedur” = katalog procedures/*.json)
# ---------------------------------------------------------------------------

def save_procedure(proc: dict, overwrite: bool = True) -> Path:
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    path = PROC_DIR / f"{proc['id']}.json"
    if path.exists() and not overwrite:
        raise FileExistsError(path)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(proc, fh, ensure_ascii=False, indent=2)
    return path


def list_procedures() -> list:
    out = []
    if not PROC_DIR.exists():
        return out
    for f in sorted(PROC_DIR.glob("*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
            out.append({
                "id": d.get("id", f.stem),
                "name": d.get("name", f.stem),
                "vehicle": d.get("vehicle", ""),
                "created": d.get("created", ""),
                "steps": len(d.get("steps", [])),
                "security": bool(d.get("security", {}).get("detected")),
                "file": f.name,
            })
        except Exception:  # noqa: BLE001
            continue
    return out


def load_procedure(name_or_id: str) -> dict:
    key = slug(name_or_id)
    path = PROC_DIR / f"{key}.json"
    if not path.exists():
        for f in PROC_DIR.glob("*.json"):
            if f.stem == name_or_id:
                path = f
                break
    if not path.exists():
        raise FileNotFoundError(f"Nie ma procedury {name_or_id!r} w {PROC_DIR}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def delete_procedure(name_or_id: str) -> Path:
    key = slug(name_or_id)
    path = PROC_DIR / f"{key}.json"
    if not path.exists():
        raise FileNotFoundError(f"Nie ma procedury {name_or_id!r} w {PROC_DIR}")
    path.unlink()
    return path
