"""obd_log.py - sesje OBD w kontrakcie ``obd-logger/1``: zapis, odczyt, analiza.

* ``SessionWriter`` - zapis sesji PID (JSONL: meta + rekordy pid) — uzywany
  przez GUI (monitor) i CLI (``obd monitor --save``); ten sam format co
  firmware loggera ESP32 (``obd-logger/docs/integracja-mirican.md``).
* ``parse_session`` / ``session_stats`` / ``series`` - odczyt i analiza
  (statystyki per PID + seria do wykresu).
* ``fetch_manifest`` / ``fetch_file`` - pobieranie sesji z loggera ESP32
  po WiFi (HTTP + mDNS; kontrakt: ``GET /manifest.json``, ``GET /files/<n>``).
* ``load_logger_config`` / ``save_logger_config`` - ustawienia loggera
  (``config/logger.json``; szkielet pod przyszle synchronizacje z ESP32).
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import LOGS_DIR, ROOT

FORMAT = "obd-logger/1"
TZ = "Europe/Warsaw"

CONFIG_DIR = ROOT / "config"
LOGGER_CFG = CONFIG_DIR / "logger.json"
DEFAULT_LOGGER_CFG = {"pids": ["010C", "010D", "0105", "012F"], "interval": 0.5,
                      "target": "pc", "note": ""}


# ---------------------------------------------------------------------------
# Zapis sesji
# ---------------------------------------------------------------------------

class SessionWriter:
    """Zapisuje sesje PID w formacie obd-logger/1 (wlasny plik na sesje)."""

    def __init__(self, directory=None, *, vehicle: str = "PC",
                 adapter: str = "ELM327", pids=()):
        d = Path(directory) if directory else LOGS_DIR
        d.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = d / f"obd_{stamp}.jsonl"
        n = 1
        while path.exists():  # dwie sesje w tej samej sekundzie
            n += 1
            path = d / f"obd_{stamp}_p{n}.jsonl"
        self.path = path
        self._fh = open(path, "a", encoding="utf-8")
        self._line({"kind": "meta", "format": FORMAT, "vehicle": vehicle,
                    "adapter": adapter, "created": int(time.time() * 1000),
                    "tz": TZ, "pids": [str(p) for p in pids]})

    def _line(self, obj: dict) -> None:
        self._fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self._fh.flush()

    def pid(self, pid: str, name: str, value, unit: str, t_ms: int | None = None) -> None:
        self._line({"kind": "pid", "t": int(t_ms if t_ms is not None else time.time() * 1000),
                    "pid": pid, "name": name, "value": value, "unit": unit})

    def event(self, event: str, data: dict | None = None) -> None:
        rec = {"kind": "event", "t": int(time.time() * 1000), "e": event}
        if data:
            rec["data"] = data
        self._line(rec)

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Odczyt i analiza
# ---------------------------------------------------------------------------

def parse_session(path):
    """(meta, rekordy) z pliku sesji; uszkodzone linie sa pomijane."""
    meta = None
    records = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                if obj.get("kind") == "meta":
                    meta = obj
                else:
                    records.append(obj)
    return meta, records


def list_obd_logs(limit: int = 100):
    """Lista sesji obd_*.jsonl w logs/ (najnowsze pierwsze)."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(LOGS_DIR.glob("obd_*.jsonl"),
                   key=lambda f: f.stat().st_mtime, reverse=True)
    out = []
    for f in files[:limit]:
        st = f.stat()
        out.append({"name": f.name, "size": st.st_size, "mtime": int(st.st_mtime)})
    return out


def session_stats(records) -> dict:
    """Statystyki per PID: liczba, min/max/srednia, zakres czasu; + czas calkowity."""
    per: dict = {}
    ts = []
    for r in records:
        if r.get("kind") != "pid":
            continue
        v = r.get("value")
        t = r.get("t")
        if isinstance(t, (int, float)):
            ts.append(t)
        if not isinstance(v, (int, float)):
            continue
        pid = str(r.get("pid") or "?")
        d = per.setdefault(pid, {"pid": pid, "name": r.get("name", ""),
                                 "unit": r.get("unit", ""), "count": 0,
                                 "min": v, "max": v, "sum": 0.0,
                                 "first": t, "last": t})
        d["count"] += 1
        d["min"] = min(d["min"], v)
        d["max"] = max(d["max"], v)
        d["sum"] += v
        d["last"] = t
    rows = []
    for d in sorted(per.values(), key=lambda x: x["pid"]):
        d["avg"] = round(d["sum"] / d["count"], 3) if d["count"] else 0.0
        d.pop("sum", None)
        d["min"] = round(d["min"], 3)
        d["max"] = round(d["max"], 3)
        rows.append(d)
    duration = round((max(ts) - min(ts)) / 1000.0, 2) if len(ts) > 1 else None
    return {"pids": rows, "duration_s": duration, "records": len(records)}


def series(records, pid: str, max_points: int = 800) -> dict:
    """Seria (t, v) do wykresu, z prostym podproblkowaniem do ``max_points``."""
    pts = []
    for r in records:
        if r.get("kind") != "pid" or str(r.get("pid")) != str(pid):
            continue
        t, v = r.get("t"), r.get("value")
        if isinstance(t, (int, float)) and isinstance(v, (int, float)):
            pts.append((t, v))
    full = len(pts)
    if full > max(2, max_points):
        k = full / max(2, max_points)
        pts = [pts[int(i * k)] for i in range(max(2, max_points))]
    return {"pid": pid, "t": [p[0] for p in pts], "v": [p[1] for p in pts],
            "count": len(pts), "records": full}


# ---------------------------------------------------------------------------
# Logger ESP32 przez WiFi (kontrakt: manifest.json + /files/<n>)
# ---------------------------------------------------------------------------

def fetch_manifest(url: str, timeout: float = 4.0) -> dict:
    """GET <url>/manifest.json (lista plikow z loggera ESP32)."""
    base = (url or "").strip().rstrip("/")
    if not base:
        return {"ok": False, "error": "Podaj adres loggera (np. http://obd-logger.local)"}
    if not re.match(r"^https?://", base):
        base = "http://" + base
    try:
        with urllib.request.urlopen(base + "/manifest.json", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8-sig", "replace"))
    except urllib.error.URLError as exc:
        return {"ok": False, "error": f"logger nieosiagalny: {getattr(exc, 'reason', exc)}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, list):
        return {"ok": False, "error": "manifest bez listy plikow"}
    clean = []
    for f in files:
        if isinstance(f, dict) and f.get("name"):
            clean.append({"name": str(f["name"]),
                          "size": int(f.get("size") or 0),
                          "mtime": int(f.get("mtime") or 0)})
    return {"ok": True, "url": base, "files": clean}


_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def fetch_file(url: str, name: str, dest_dir=None, max_bytes: int = 64 * 1024 * 1024) -> dict:
    """Pobiera plik z loggera do logs/ (nazwa: bezpieczna, bez sciezek)."""
    base = (url or "").strip().rstrip("/")
    if not base:
        return {"ok": False, "error": "Podaj adres loggera"}
    if not re.match(r"^https?://", base):
        base = "http://" + base
    safe = Path(str(name)).name
    if not safe or not _SAFE_NAME.match(safe):
        return {"ok": False, "error": f"Niebezpieczna nazwa pliku: {name!r}"}
    dest_dir = Path(dest_dir) if dest_dir else LOGS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe
    try:
        with urllib.request.urlopen(base + "/files/" + safe, timeout=15.0) as resp:
            size = 0
            tmp = dest.with_suffix(dest.suffix + ".part")
            with open(tmp, "wb") as fh:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("plik przekracza limit rozmiaru")
                    fh.write(chunk)
            tmp.replace(dest)
    except urllib.error.URLError as exc:
        return {"ok": False, "error": f"logger nieosiagalny: {getattr(exc, 'reason', exc)}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "file": safe, "size": size}


# ---------------------------------------------------------------------------
# Konfiguracja loggera (config/logger.json)
# ---------------------------------------------------------------------------

def load_logger_config() -> dict:
    cfg = dict(DEFAULT_LOGGER_CFG)
    if LOGGER_CFG.exists():
        try:
            with open(LOGGER_CFG, encoding="utf-8") as fh:
                data = json.load(fh) or {}
            if isinstance(data, dict):
                cfg.update(data)
        except Exception:  # noqa: BLE001
            pass
    return cfg


def save_logger_config(data: dict) -> dict:
    cfg = dict(DEFAULT_LOGGER_CFG)
    if isinstance(data, dict):
        pids = data.get("pids")
        if isinstance(pids, list):
            clean = []
            for p in pids[:32]:
                s = str(p).strip().upper()
                if re.fullmatch(r"01[0-9A-F]{2}|[0-9A-F]{2}", s):
                    clean.append(s)
            cfg["pids"] = clean or DEFAULT_LOGGER_CFG["pids"]
        try:
            cfg["interval"] = max(0.05, min(60.0, float(data.get("interval", cfg["interval"]))))
        except (TypeError, ValueError):
            pass
        if data.get("target") in ("pc", "esp32"):
            cfg["target"] = data["target"]
        if isinstance(data.get("note"), str):
            cfg["note"] = data["note"][:200]
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOGGER_CFG, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    return cfg


# ---------------------------------------------------------------------------
# Stan adaptera (szybsze kolejne polaczenia): config/obd.json
# ---------------------------------------------------------------------------

OBD_STATE = CONFIG_DIR / "obd.json"


def load_obd_state() -> dict:
    """Zapamietany stan adaptera (protokol, port) - odporny na braki/uszkodzenia."""
    if OBD_STATE.exists():
        try:
            with open(OBD_STATE, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except Exception:  # noqa: BLE001
            pass
    return {}


def save_obd_state(data: dict) -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cur = load_obd_state()
    cur.update(data or {})
    with open(OBD_STATE, "w", encoding="utf-8") as fh:
        json.dump(cur, fh, ensure_ascii=False, indent=2)
    return cur
