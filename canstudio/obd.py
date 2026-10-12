"""obd.py - warstwa OBD-II: PID-y (tryb 01), DTC (03/04), VIN (09 02).

Uzywane z adapterami ELM327 (np. vLinker MS) przez ``canstudio.elm327``.
Tabela PID i dekodery jak w firmware loggera OBD (obd_pids.c) - jeden
sposob liczenia w calym ekosystemie miriCAN.
"""

from __future__ import annotations

import re
import threading
import time

from . import obd_log
from .elm327 import Elm327, find_elm_port
from .obd_log import SessionWriter

# ---------------------------------------------------------------------------
# Dekodery (SAE J1979, tryb 01) - zgodne z firmware loggera
# ---------------------------------------------------------------------------

def _u8(d):
    return float(d[0])


def _u16(d):
    return float(d[0] * 256 + d[1])


def _pct(d):
    return d[0] * 100.0 / 255.0


def _temp(d):
    return d[0] - 40.0


def _rpm(d):
    return (d[0] * 256 + d[1]) / 4.0


def _kph(d):
    return float(d[0])


def _kpa(d):
    return float(d[0])


def _maf(d):
    return (d[0] * 256 + d[1]) / 100.0


def _volt(d):
    return (d[0] * 256 + d[1]) / 1000.0


def _lambda(d):
    return 2.0 / 65536.0 * (d[0] * 256 + d[1])


def _fuel_rate(d):
    return (d[0] * 256 + d[1]) / 20.0


def _sec(d):
    return float(d[0] * 256 + d[1])


def _km(d):
    return float(d[0] * 256 + d[1])


def _milcount(d):
    return float(d[0] & 0x7F)


#: PID -> (nazwa, jednostka, liczba_bajtow, dekoder)
PID_TABLE = {
    0x01: ("MIL_DTC_Count", "", 4, _milcount),
    0x03: ("FuelSystemStatus", "code", 2, _u16),
    0x04: ("EngineLoad", "%", 1, _pct),
    0x05: ("CoolantTemp", "C", 1, _temp),
    0x0A: ("FuelPressure", "kPa", 1, _kpa),
    0x0B: ("IntakeMAP", "kPa", 1, _kpa),
    0x0C: ("EngineRPM", "rpm", 2, _rpm),
    0x0D: ("VehicleSpeed", "km/h", 1, _kph),
    0x0F: ("IntakeTemp", "C", 1, _temp),
    0x10: ("MAF", "g/s", 2, _maf),
    0x11: ("ThrottlePos", "%", 1, _pct),
    0x13: ("O2SensorsPresent", "bitmap", 1, _u8),
    0x1C: ("OBDStandard", "code", 1, _u8),
    0x1F: ("RunTime", "s", 2, _sec),
    0x21: ("DistWithMIL", "km", 2, _km),
    0x2F: ("FuelLevel", "%", 1, _pct),
    0x30: ("WarmupsSinceClear", "count", 1, _u8),
    0x31: ("DistSinceClear", "km", 2, _km),
    0x33: ("BaroPressure", "kPa", 1, _kpa),
    0x42: ("ModuleVoltage", "V", 2, _volt),
    0x44: ("CommandedLambda", "lambda", 2, _lambda),
    0x45: ("RelThrottlePos", "%", 1, _pct),
    0x46: ("AmbientTemp", "C", 1, _temp),
    0x49: ("AccelPedalD", "%", 1, _pct),
    0x4A: ("AccelPedalE", "%", 1, _pct),
    0x4C: ("AccelPedalF", "%", 1, _pct),
    0x4D: ("TimeSinceMIL", "min", 2, _sec),
    0x51: ("FuelType", "code", 1, _u8),
    0x5C: ("OilTemp", "C", 1, _temp),
    0x5E: ("FuelRate", "L/h", 2, _fuel_rate),
}


def pid_name(pid: int) -> str:
    ent = PID_TABLE.get(pid & 0xFF)
    return ent[0] if ent else "PID_UNKNOWN"


def norm_pid(text: str) -> int:
    """'010C' / '0C' / '0x0C' -> 0x0C.

    Tolerancja na PowerShell: '0105' na liscie rozdzielanej przecinkami potrafi
    przyjsc jako '105' (PS potraktowal token jako liczbe i zjadl wiodace zero).
    """
    s = str(text).strip().lower().replace("0x", "")
    m = re.fullmatch(r"1(\d\d)", s)
    if m:
        s = "01" + m.group(1)
    if len(s) == 4 and s.startswith("01"):
        s = s[2:]
    v = int(s, 16)
    if not 0 <= v <= 0xFF:
        raise ValueError(f"PID poza zakresem: {text!r}")
    return v


# ---------------------------------------------------------------------------
# Parsowanie odpowiedzi ELM
# ---------------------------------------------------------------------------

_HEXCHARS = set("0123456789abcdefABCDEF")


def collect_bytes(resp: str) -> list:
    """Bajty z tekstu odpowiedzi ELM.

    Pomija tokeny ID (3 lub 8 znakow hex, np. '7E8', '18DAF110'); zbiera
    tokeny 1-2 znakowe jako bajty (odporne na ATH0/ATH1 i PCI).
    """
    out = []
    for tok in resp.replace("\n", " ").replace("\t", " ").split():
        tok = tok.strip(",;")
        if not tok:
            continue
        allhex = all(c in _HEXCHARS for c in tok)
        if len(tok) in (3, 8) and allhex:
            continue
        if len(tok) <= 2 and allhex:
            out.append(int(tok, 16))
    return out


def _tokens_to_bytes(tokens) -> list | None:
    out = []
    for t in tokens:
        t = t.strip(",;")
        if not t:
            continue
        if len(t) <= 2 and all(c in _HEXCHARS for c in t):
            out.append(int(t, 16))
        else:
            return None
    return out


def payloads_from_resp(resp: str) -> list:
    """ISO-TP payloady z tekstu odpowiedzi ELM (SF/FF/CF scalane, wiele ECU).

    Bufory First/Consecutive trzymane SA PER ECU (linie dwoch sterownikow
    moga sie przeplatać, np. '7E9 10 08 ...' / '7E8 10 0A ...').
    """
    out: list = []
    curs: dict = {}
    for line in (resp or "").split("\n"):
        toks = [t for t in line.replace("\t", " ").split() if t]
        if not toks:
            continue
        key = None
        if len(toks[0]) in (3, 8) and all(c in _HEXCHARS for c in toks[0]):
            key = toks[0].upper()  # ID ramki (7E8 / 18DAF110)
            toks = toks[1:]
        b = _tokens_to_bytes(toks)
        if not b:
            continue
        pci = b[0]
        if pci & 0xF0 == 0x00:  # Single Frame
            ln = pci & 0x0F
            if 0 < ln <= len(b) - 1:
                out.append(bytes(b[1:1 + ln]))
            curs.pop(key, None)
        elif pci & 0xF0 == 0x10:  # First Frame
            ln = ((pci & 0x0F) << 8) | (b[1] if len(b) > 1 else 0)
            cur = {"left": ln, "buf": bytearray(b[2:])}
            curs[key] = cur
            if len(cur["buf"]) >= ln:
                out.append(bytes(cur["buf"][:ln]))
                curs.pop(key, None)
        elif pci & 0xF0 == 0x20 and key in curs:  # Consecutive Frame
            cur = curs[key]
            cur["buf"] += bytes(b[1:])
            if len(cur["buf"]) >= cur["left"]:
                out.append(bytes(cur["buf"][:cur["left"]]))
                curs.pop(key, None)
    return out


def parse_payload(payload: bytes) -> dict:
    """[41 pid1 dane1 pid2 dane2 ...] -> {pid: (wartosc, dane)}."""
    out: dict = {}
    b = list(payload)
    try:
        i = b.index(0x41) + 1
    except ValueError:
        return out
    while i < len(b):
        pid = b[i]
        i += 1
        ent = PID_TABLE.get(pid)
        if ent is None:
            break
        nb = ent[2]
        if i + nb > len(b):
            break
        data = bytes(b[i:i + nb])
        i += nb
        out[pid] = (ent[3](data), data)
    return out


def parse_pid(resp: str, pid: int):
    """Szuka '41 <pid>' w odpowiedzi; zwraca (wartosc, surowe_bajty) lub None."""
    pid &= 0xFF
    ent = PID_TABLE.get(pid)
    if ent is None:
        return None
    _name, _unit, nb, fn = ent
    b = collect_bytes(resp)
    for i in range(len(b) - 1):
        if b[i] == 0x41 and b[i + 1] == pid and len(b) >= i + 2 + nb:
            data = bytes(b[i + 2:i + 2 + nb])
            return fn(data), data
    return None


def classify_resp(resp: str) -> str:
    """'ok' | 'bus' | 'nodata' | 'err' - do komunikatow narzedzia."""
    u = (resp or "").upper().replace(" ", "")
    if "UNABLETOCONNECT" in u or "CANERROR" in u or "BUSINIT" in u:
        return "bus"
    if "NODATA" in u:
        return "nodata"
    return "err"


def parse_voltage(text: str):
    """'12.2V' -> 12.2 (albo None)."""
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*V", text or "")
    return float(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# DTC (tryb 03 / kasowanie 04)
# ---------------------------------------------------------------------------

def decode_dtc(b1: int, b2: int) -> str:
    """Dwa bajty DTC -> np. 'P0123' (konwencja OBD-II)."""
    letter = "PCBU"[(b1 >> 6) & 0x03]
    return f"{letter}{(b1 >> 4) & 0x03}{b1 & 0x0F:X}{b2 >> 4:X}{b2 & 0x0F:X}"


def parse_dtc(resp: str) -> list:
    """Lista kodow z odpowiedzi trybu 03.

    Parsujemy PER LINIA (kazda odpowiedz ECU osobno) - na magistrali moze
    odpowiedziec kilka sterownikow (np. 7E8 i 7E9); zlepianie bajtow z dwoch
    linii tworzylo kiedys falszywe kody. '43 00' (pojedynczy bajt) = brak kodow.
    Zwraca unikalne kody (zachowana kolejnosc).
    """
    codes = []
    for line in (resp or "").split("\n"):
        b = collect_bytes(line)
        try:
            i = b.index(0x43) + 1
        except ValueError:
            continue
        while i + 1 < len(b):
            b1, b2 = b[i], b[i + 1]
            if b1 == 0 and b2 == 0:
                break  # wypelnienie
            codes.append(decode_dtc(b1, b2))
            i += 2
    return list(dict.fromkeys(codes))


# ---------------------------------------------------------------------------
# VIN (tryb 09 PID 02)
# ---------------------------------------------------------------------------

def parse_vin(resp: str):
    """VIN z odpowiedzi '49 02 ...' (wielolinijkowe odsiane przez collect_bytes)."""
    b = collect_bytes(resp)
    for i in range(len(b) - 2):
        if b[i] == 0x49 and b[i + 1] == 0x02:
            j = i + 2
            if j < len(b) and b[j] == 0x01:  # NODI
                j += 1
            # VIN: tylko znaki [0-9A-Z] (odsiewa m.in. bajty PCI ramek CF: 0x21..0x2F)
            chars = [chr(v) for v in b[j:] if 0x30 <= v <= 0x39 or 0x41 <= v <= 0x5A]
            s = "".join(chars)
            if len(s) >= 10:
                return s[:17]
            return s or None
    return None


# ---------------------------------------------------------------------------
# Wysokopoziomowe operacje na kliencie Elm327
# ---------------------------------------------------------------------------

def _ask(elm, svc_pid: str, timeout: float | None = None) -> str:
    """Zadanie z dokladka czasu, gdy adapter dopiero szuka protokolu.

    'SEARCHING...' bez 'UNABLE TO CONNECT' = przerwany search - probujemy
    jeszcze do 2 razy z wiekszym timeoutem (adapter musi zdazyc znalezc
    protokol, gl. po swiezym ATZ).
    """
    resp = elm.obd(svc_pid, timeout=timeout)
    for _ in range(2):
        u = (resp or "").upper()
        if "SEARCHING" in u and "UNABLE" not in u:
            resp2 = elm.obd(svc_pid, timeout=max(timeout or 0.0, 12.0))
            if not resp2.strip():
                break
            resp = resp2
        else:
            break
    return resp


def read_pid(elm, pid: int, timeout: float | None = None) -> dict:
    """Odczyt jednego PID; zwraca dict z polem 'status' (ok/nodata/bus/err)."""
    cmd = f"01{pid:02X}"
    resp = _ask(elm, cmd, timeout=timeout)
    ent = PID_TABLE.get(pid & 0xFF)
    out = {"pid": cmd, "name": ent[0] if ent else "PID_UNKNOWN",
           "unit": ent[1] if ent else "", "value": None, "data": "", "status": "err"}
    parsed = parse_pid(resp, pid)
    if parsed is not None:
        out["value"] = round(parsed[0], 3)
        out["data"] = parsed[1].hex().upper()
        out["status"] = "ok"
    else:
        st = classify_resp(resp)
        if st in ("bus", "nodata"):
            out["status"] = st
        # gdy PID poza tabela, ale odpowiedz ma 41 pid - surowa wartosc
        if out["status"] == "err":
            b = collect_bytes(resp)
            for i in range(len(b) - 1):
                if b[i] == 0x41 and b[i + 1] == (pid & 0xFF):
                    out["data"] = bytes(b[i + 2:i + 6]).hex(" ").upper()
                    out["status"] = "ok"
                    break
    return out


def _row_placeholder(pid: int, status: str) -> dict:
    ent = PID_TABLE.get(pid & 0xFF)
    return {"pid": f"01{pid:02X}", "name": ent[0] if ent else "PID_UNKNOWN",
            "unit": ent[1] if ent else "", "value": None, "data": "",
            "status": status}


def read_pids(elm, pids, timeout: float | None = None, chunk: int = 6) -> list:
    """Odczyt listy PID-ow - BATCH: do ``chunk`` PID-ow w jednej komendzie.

    Znacznie szybciej niz PID-po-PIDzie (jedno polecenie na grupe); brakujace
    PID-y dociagamy pojedynczo (fallback). Kolejnosc wyniku = lista wejsciowa.
    """
    pids = [int(p) & 0xFF for p in pids]
    rows: dict = {}
    step = max(1, int(chunk))
    for start in range(0, len(pids), step):
        group = pids[start:start + step]
        known = [p for p in group if p in PID_TABLE]
        for p in group:  # PID-y bez dekodera w tabeli: odczyt pojedynczy (surowy)
            if p not in PID_TABLE:
                rows[p] = read_pid(elm, p, timeout=timeout)
        if not known:
            continue
        cmd = "01" + "".join(f"{p:02X}" for p in known)
        resp = _ask(elm, cmd, timeout=timeout)
        parsed: dict = {}
        for pl in payloads_from_resp(resp):
            for k, v in parse_payload(pl).items():
                parsed.setdefault(k, v)
        missing = []
        for p in known:
            if p in parsed:
                ent = PID_TABLE.get(p)
                val, data = parsed[p]
                rows[p] = {"pid": f"01{p:02X}",
                           "name": ent[0] if ent else "PID_UNKNOWN",
                           "unit": ent[1] if ent else "",
                           "value": round(val, 3),
                           "data": data.hex().upper(), "status": "ok"}
            else:
                missing.append(p)
        if missing:
            if classify_resp(resp) == "bus":
                for p in missing:
                    rows[p] = _row_placeholder(p, "bus")
            else:
                for p in missing:
                    rows[p] = read_pid(elm, p, timeout=timeout)
        if start + step < len(pids):
            time.sleep(0.02)
    return [rows[p] for p in pids]


def read_supported(elm) -> list:
    """Zbior numerow PID wspieranych przez ECU (0100/0120/0140...)."""
    pids = set()
    base = 0x00
    for _ in range(5):
        resp = _ask(elm, f"01{base:02X}", timeout=6.0)
        b = collect_bytes(resp)
        data = None
        for i in range(len(b) - 1):
            if b[i] == 0x41 and b[i + 1] == base and len(b) >= i + 6:
                data = b[i + 2:i + 6]
                break
        if data is None:
            break
        val = int.from_bytes(bytes(data), "big")
        for k in range(32):
            if val & (1 << (31 - k)):
                pids.add(base + 1 + k)
        base += 0x20
        if base not in pids:
            break
    return sorted(pids)


def read_dtc(elm):
    """Odczyt DTC (tryb 03): zwraca ``(kody, surowa_odpowiedz)``.

    Pusta lista + odpowiedz z '43' = zero kodow; pusta lista bez '43' =
    brak odpowiedzi magistrali.
    """
    resp = _ask(elm, "03", timeout=8.0)
    return parse_dtc(resp), resp or ""


def clear_dtc(elm) -> str:
    """Kasowanie DTC (tryb 04). Zwraca surowa odpowiedz ('' gdy brak)."""
    return elm.obd("04", timeout=8.0)


def read_vin(elm) -> str | None:
    """VIN z ECU (tryb 09 PID 02)."""
    resp = _ask(elm, "0902", timeout=12.0)
    return parse_vin(resp)


# ---------------------------------------------------------------------------
# Sesja trzymana (GUI/CLI): otwarty adapter + monitor + zapis obd-logger/1
# ---------------------------------------------------------------------------

def _pids_to_nums(pids) -> list:
    """['010C','0D'] / '010C,0D' -> [0x0C, 0x0D]."""
    if isinstance(pids, str):
        parts = re.split(r"[\s,;]+", pids)
    else:
        parts = []
        for x in pids or []:
            parts.extend(re.split(r"[\s,;]+", str(x)))
    out = []
    for p in parts:
        p = p.strip()
        if p:
            out.append(norm_pid(p))
    return out


class ObdSession:
    """Sesja OBD na adapterze ELM327 (dla GUI i CLI).

    * ``open`` / ``close`` - trzyma otwarty adapter miedzy zapytaniami,
    * ``read`` / ``info`` / ``dtc`` - operacje jednorazowe,
    * ``monitor_start`` / ``monitor_stop`` - ciagly odczyt PID-ow w watku,
      z opcjonalnym zapisem sesji (``obd_log.SessionWriter``),
    * ``push(event)`` - opcjonalny callback zdarzen (strumien GUI).
    """

    def __init__(self, opener=None, push=None):
        self._opener = opener
        self.push = push
        self._lock = threading.RLock()
        self.elm = None
        self.port: str | None = None
        self.adapter = ""
        self.voltage = None
        self.bus_ok = None
        self._supported = None
        self._mon: threading.Thread | None = None
        self._mon_stop = threading.Event()
        self._mon_state: dict = {"active": False, "pids": [], "interval": 0.0,
                                 "saved": None, "rounds": 0}

    # -- zdarzenia --
    def _emit(self, ev: dict) -> None:
        if self.push:
            try:
                self.push(ev)
            except Exception:  # noqa: BLE001
                pass

    def _need(self):
        if self.elm is None:
            raise RuntimeError("Sesja OBD nie jest polaczona.")
        return self.elm

    # -- polaczenie --
    def _init_seq(self, elm, protocol: str | None = None) -> dict:
        """Sekwencja startowa; protocol (np. '6') -> od razu ATSP<n> (bez szukania)."""
        elm.cmd("ATZ", timeout=8.0)
        for c in ("ATE0", "ATL0", "ATS1", "ATH1", "ATAT1"):
            elm.cmd(c)
        elm.cmd(f"ATSP{protocol}" if protocol else "ATSP0")
        ad = (elm.cmd("ATI") or "").strip().splitlines()
        return {"adapter": ad[-1] if ad else "?", "voltage": elm.cmd("ATRV")}

    def open(self, port=None, baud: int = 115200, timeout: float = 3.0,
             warm_timeout: float = 25.0) -> dict:
        with self._lock:
            if self.elm is not None:
                return {"ok": True, "already": True, **self.status()}
            why = "autodetekcja"
            p = port
            if not p:
                p, why = find_elm_port()
            if not p:
                return {"ok": False,
                        "error": "Nie znaleziono portu adaptera ELM (vLinker) - podaj port."}
            state = obd_log.load_obd_state()
            fast = str(state.get("protocol") or "").strip() or None
            elm = Elm327(p, baud=baud, timeout=timeout, opener=self._opener)
            try:
                elm.open()
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"Nie moge otworzyc {p}: {exc}"}
            try:
                info = self._init_seq(elm, fast)
                warm = elm.obd("0100", timeout=10.0 if fast else warm_timeout)
                u = warm.upper().replace(" ", "")
                bus_ok = ("4100" in u) and ("UNABLETOCONNECT" not in u)
                if fast and not bus_ok:
                    # zapamietany protokol nie pasuje (inne auto?) - pelny auto-search
                    info = self._init_seq(elm, None)
                    warm = elm.obd("0100", timeout=warm_timeout)
                    u = warm.upper().replace(" ", "")
                    bus_ok = ("4100" in u) and ("UNABLETOCONNECT" not in u)
                    fast = None
            except Exception as exc:  # noqa: BLE001
                try:
                    elm.close()
                except Exception:  # noqa: BLE001
                    pass
                return {"ok": False, "error": f"Blad inicjalizacji: {exc}"}
            if bus_ok and self._opener is None:  # nie zapisuj stanu, gdy opener jest wstrzykniety (testy)
                if not fast:
                    m = re.search(r"(\d)\s*$", (elm.cmd("ATDPN", timeout=2.0) or "").strip())
                    if m and m.group(1) != "0":
                        obd_log.save_obd_state({"protocol": m.group(1), "port": p})
                else:
                    obd_log.save_obd_state({"port": p})
            self.adapter = info.get("adapter") or "?"
            self.voltage = parse_voltage(info.get("voltage", ""))
            self.bus_ok = bus_ok
            self.elm = elm
            self._supported = None
            self.port = p
            out = {"ok": True, "port": p, "why": why, "adapter": self.adapter,
                   "voltage": self.voltage, "bus": self.bus_ok,
                   "fast": bool(fast)}
            self._emit({"t": "obd", "e": "state", "open": True, "port": p,
                        "adapter": self.adapter, "voltage": self.voltage,
                        "bus": self.bus_ok})
            return out

    def close(self) -> None:
        self.monitor_stop()
        with self._lock:
            if self.elm is not None:
                try:
                    self.elm.close()
                except Exception:  # noqa: BLE001
                    pass
            self.elm = None
            self.port = None
            self.bus_ok = None
            self._supported = None
        self._emit({"t": "obd", "e": "state", "open": False})

    def status(self) -> dict:
        mon = dict(self._mon_state)
        if self._mon is not None and not self._mon.is_alive():
            mon["active"] = False
        return {"open": self.elm is not None, "port": self.port,
                "adapter": self.adapter, "voltage": self.voltage,
                "bus": self.bus_ok, "monitor": mon}

    # -- operacje jednorazowe --
    def supported_pids(self) -> list:
        """PID-y wspierane przez auto (cache na czas sesji; [] gdy brak)."""
        with self._lock:
            if self.elm is None:
                return []
            if self._supported is None:
                try:
                    self._supported = read_supported(self.elm)
                except Exception:  # noqa: BLE001
                    self._supported = []
            return list(self._supported)

    def read(self, pids) -> dict:
        try:
            with self._lock:
                elm = self._need()
                nums = _pids_to_nums(pids)
                if not nums:
                    return {"ok": False, "error": "Nie podano PID-ow."}
                rows = read_pids(elm, nums)
            return {"ok": True, "port": self.port, "rows": rows}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def info(self) -> dict:
        try:
            with self._lock:
                elm = self._need()
                vin = read_vin(elm)
                supported = read_supported(elm)
            return {"ok": True, "port": self.port, "vin": vin,
                    "supported": supported, "count": len(supported),
                    "adapter": self.adapter, "voltage": self.voltage,
                    "bus": self.bus_ok}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def dtc(self, clear: bool = False, confirm: bool = False) -> dict:
        if clear and not confirm:
            return {"ok": False,
                    "error": "Kasowanie DTC wymaga potwierdzenia (confirm=true)."}
        try:
            with self._lock:
                elm = self._need()
                codes, raw = read_dtc(elm)
                cleared = None
                if clear:
                    resp = clear_dtc(elm)
                    cleared = bool(("44" in resp) or ("OK" in resp.upper()))
            if clear:
                self._emit({"t": "obd", "e": "line",
                            "m": "kasowanie DTC: " + ("OK" if cleared else "brak potwierdzenia")})
            return {"ok": True, "port": self.port, "codes": codes,
                    "count": len(codes), "answered": "43" in (raw or ""),
                    "cleared": cleared}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # -- monitor --
    def monitor_start(self, pids, interval: float = 0.5, save: bool = False,
                      save_dir=None) -> dict:
        try:
            nums = _pids_to_nums(pids)
        except ValueError as exc:
            return {"ok": False, "error": f"zly PID: {exc}"}
        if not nums:
            return {"ok": False, "error": "Nie podano PID-ow."}
        interval = max(0.05, min(60.0, float(interval or 0.5)))
        with self._lock:
            if self.elm is None:
                return {"ok": False, "error": "Najpierw polacz z adapterem."}
            if self._mon is not None and self._mon.is_alive():
                return {"ok": False, "error": "Monitor juz dziala."}
            writer = None
            if save:
                writer = SessionWriter(save_dir, adapter=self.adapter or "ELM327",
                                       pids=[f"01{n:02X}" for n in nums])
            self._mon_stop = threading.Event()
            self._mon_state = {"active": True,
                               "pids": [f"01{n:02X}" for n in nums],
                               "interval": interval,
                               "saved": str(writer.path) if writer else None,
                               "rounds": 0}
            self._mon = threading.Thread(target=self._monitor_loop,
                                         args=(nums, interval, writer),
                                         name="obd-monitor", daemon=True)
            self._mon.start()
            out = {"ok": True, "pids": self._mon_state["pids"],
                   "interval": interval, "saved": self._mon_state["saved"]}
        self._emit({"t": "obd", "e": "monitor", "active": True,
                    "pids": out["pids"], "saved": out["saved"]})
        return out

    def _monitor_loop(self, nums, interval, writer) -> None:
        try:
            while not self._mon_stop.is_set():
                with self._lock:
                    if self.elm is None:
                        self._mon_stop.set()
                        break
                    rows = read_pids(self.elm, nums, timeout=3.0)
                for r in rows:
                    self._mon_state["rounds"] = self._mon_state.get("rounds", 0) + 1
                    self._emit({"t": "obd", "e": "pid", "pid": r["pid"],
                                "name": r["name"], "value": r["value"],
                                "unit": r["unit"], "status": r["status"]})
                    if writer is not None and r["status"] == "ok":
                        writer.pid(r["pid"], r["name"], r["value"], r["unit"])
                self._mon_stop.wait(interval)
        finally:
            if writer is not None:
                writer.close()
            self._mon_state["active"] = False
            self._emit({"t": "obd", "e": "monitor", "active": False,
                        "rounds": self._mon_state.get("rounds", 0),
                        "saved": self._mon_state.get("saved")})

    def monitor_stop(self) -> dict:
        t = self._mon
        if t is None or not t.is_alive():
            self._mon_state["active"] = False
            return {"ok": True, "active": False,
                    "rounds": self._mon_state.get("rounds", 0),
                    "saved": self._mon_state.get("saved")}
        self._mon_stop.set()
        t.join(timeout=20.0)
        self._mon = None
        return {"ok": True, "active": False,
                "rounds": self._mon_state.get("rounds", 0),
                "saved": self._mon_state.get("saved")}
