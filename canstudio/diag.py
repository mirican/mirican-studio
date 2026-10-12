"""Diagnostyka UDS / ISO-TP (CAN) — warstwa wspólna.

Dostarcza:
* budowę stosu ISO-TP (``can-isotp`` v2, klasa ``CanStack`` nad python-can),
* klienta UDS (``udsoncan``) z kodekiem surowym dla dowolnych DID,
* skaner ECU po magistrali (pojedyncze ramki ISO-TP — bez otwierania stosu),
* log sesji (każdy wysłany/odebrany payload -> ``logs/uds_*.log``).

Pakiety ``can-isotp`` i ``udsoncan`` są opcjonalne — reszta toolkitu działa bez nich.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import can

_DEPS_ERROR = None
try:
    import isotp
    import udsoncan
    from udsoncan.client import Client
    from udsoncan.connections import PythonIsoTpConnection
    from udsoncan.common.DidCodec import DidCodec
except Exception as exc:  # pragma: no cover
    _DEPS_ERROR = exc

HAVE_DEPS = _DEPS_ERROR is None


def require_deps() -> None:
    """Przerywa z czytelnym komunikatem, gdy brak pakietów diagnostycznych."""
    if not HAVE_DEPS:
        raise SystemExit(
            "Brak pakietów diagnostycznych (can-isotp, udsoncan).\n"
            "Zainstaluj:  py -m pip install can-isotp udsoncan\n"
            f"Szczegóły błędu: {_DEPS_ERROR}"
        )


# ---------------------------------------------------------------------------
# DID (znane identyfikatory danych wg ISO 14229; BMW używa tych samych F1xx)
# ---------------------------------------------------------------------------

DID_NAMES = {
    0xF180: "bootSoftwareIdentification",
    0xF181: "applicationSoftwareIdentification",
    0xF182: "applicationDataIdentification",
    0xF183: "bootSoftwareFingerprint",
    0xF184: "applicationSoftwareFingerprint",
    0xF185: "activeDiagnosticSession",
    0xF186: "vehicleManufacturerSparePartNumber",
    0xF187: "vehicleManufacturerECUHardwareNumber",
    0xF188: "vehicleManufacturerECUSoftwareNumber",
    0xF189: "vehicleManufacturerECUSoftwareVersionNumber",
    0xF18A: "systemSupplierIdentifier",
    0xF18B: "ecuManufacturingDate",
    0xF18C: "ecuSerialNumber",
    0xF190: "vin",
    0xF191: "vehicleManufacturerECUHardwareVersionNumber",
    0xF192: "systemSupplierECUHardwareNumber",
    0xF193: "systemSupplierECUHardwareVersionNumber",
    0xF194: "systemSupplierECUSoftwareNumber",
    0xF195: "systemSupplierECUSoftwareVersionNumber",
    0xF197: "exhaustRegulationOrTypeApprovalNumber",
    0xF198: "systemNameOrEngineType",
    0xF19E: "ecuInstallationDate",
}

#: Domyślny zestaw DID do szybkiego rozpoznania sterownika (``uds info``).
INFO_DIDS = [0xF190, 0xF18C, 0xF187, 0xF188, 0xF189, 0xF18A, 0xF18B, 0xF191]


def did_name(did: int) -> str:
    return DID_NAMES.get(did, "")


# ---------------------------------------------------------------------------
# Parsowanie argumentów hex
# ---------------------------------------------------------------------------

def parse_hex(text: str) -> int:
    """'6F1' / '0x6F1' -> int. Wszystkie wartości w UDS traktujemy jako hex."""
    s = str(text).strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    return int(s, 16)


def parse_hex_bytes(text: str) -> bytes:
    """'01 02 FF' / '0102FF' / '0x01,0x02' -> b'\\x01\\x02\\xff'."""
    s = str(text).strip().lower().replace("0x", "")
    for ch in (" ", ":", ",", "\t"):
        s = s.replace(ch, "")
    if len(s) % 2:
        raise SystemExit(f"Nieparzysta liczba cyfr hex: {text!r}")
    try:
        return bytes.fromhex(s)
    except ValueError as exc:
        raise SystemExit(f"Nieprawidłowy hex: {text!r} ({exc})")


def parse_ids_spec(text: str) -> list[int]:
    """'6F1,6F3' lub '600-6FF' (można mieszać: '6E0-6E5,700') -> lista ID."""
    ids: list[int] = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a, b = parse_hex(a), parse_hex(b)
            if b < a:
                a, b = b, a
            ids.extend(range(a, b + 1))
        else:
            ids.append(parse_hex(part))
    return ids


# ---------------------------------------------------------------------------
# ISO-TP / UDS
# ---------------------------------------------------------------------------

class RawCodec(DidCodec):
    """Kodek surowy: odczyt = wszystkie bajty odpowiedzi, zapis = bajty z CLI."""

    def encode(self, *did_value):
        if len(did_value) != 1:
            raise ValueError("oczekiwano jednej wartości")
        value = did_value[0]
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        return parse_hex_bytes(str(value))

    def decode(self, did_payload: bytes) -> bytes:
        return bytes(did_payload)

    def __len__(self):
        raise DidCodec.ReadAllRemainingData


CLIENT_CONFIG = {
    "exception_on_negative_response": False,
    "exception_on_invalid_response": False,
    "exception_on_unexpected_response": False,
    "p2_timeout": 2.0,
    "p2_star_timeout": 6.0,
    "data_identifiers": {"default": RawCodec()},
}


class LoggedConnection(PythonIsoTpConnection):
    """Połączenie ISO-TP logujące każdy wysłany i odebrany payload."""

    def __init__(self, tp, log=None):
        super().__init__(tp)
        self._log = log

    def specific_send(self, payload, timeout=None):
        if self._log is not None:
            self._log.tx(payload)
        return super().specific_send(payload, timeout)

    def specific_wait_frame(self, timeout=None):
        frame = super().specific_wait_frame(timeout)
        if self._log is not None and frame is not None:
            self._log.rx(frame)
        return frame


def open_isotp(bus, txid: int, rxid: int, extended: bool = False, params=None):
    """Tworzy stos ISO-TP nad magistralą python-can (jeszcze nieuruchomiony).

    Uruchamia go ``PythonIsoTpConnection.open()`` (wywoływane w ``make_client``).
    """
    params = dict(params or {})
    params.setdefault("blocksize", 0)
    params.setdefault("stmin", 0)
    params.setdefault("tx_padding", 0x00)  # klasyczne testery dosyłają do 8 bajtów
    mode = (isotp.AddressingMode.Normal_29bits if extended
            else isotp.AddressingMode.Normal_11bits)
    address = isotp.Address(mode, txid=txid, rxid=rxid)
    return isotp.CanStack(bus=bus, address=address, params=params)


def make_client(tp, log=None):
    """Zamyka stos w klienta UDS. Zwraca ``(client, connection)``; nie startuje busu."""
    # NRC (odpowiedzi negatywne) raportujemy sami w CLI — loger klienta wyciszony.
    logging.getLogger("UdsClient").setLevel(logging.CRITICAL)
    conn = LoggedConnection(tp, log)
    conn.open()
    client = Client(conn, config=CLIENT_CONFIG)
    return client, conn


def close_session(bus=None, tp=None, conn=None) -> None:
    """Bezpieczne zamknięcie w odwrotnej kolejności (każdy krok best-effort)."""
    for fn in (
        (lambda: conn.close()) if conn is not None else None,
        (lambda: tp.stop()) if tp is not None else None,
        (lambda: bus.shutdown()) if bus is not None else None,
    ):
        if fn is None:
            continue
        try:
            fn()
        except Exception:  # noqa: BLE001 - zamykanie best-effort
            pass


def code_name(code: int) -> str:
    """0x31 -> 'RequestOutOfRange' (nazwa z udsoncan), fallback '0x31'."""
    cls = udsoncan.ResponseCode.ResponseCode
    for name in dir(cls):
        if name.startswith("_"):
            continue
        value = getattr(cls, name)
        if isinstance(value, int) and value == code:
            return name
    return f"0x{code:02X}"


def did_value(r, did: int):
    """Wartość DID z odpowiedzi RDBI (bez echo DID); zwykle bytes."""
    sd = getattr(r, "service_data", None)
    values = getattr(sd, "values", None)
    if isinstance(values, dict):
        val = values.get(did)
        if val is None and len(values) == 1:
            val = next(iter(values.values()))
        if val is not None:
            return bytes(val) if isinstance(val, (bytes, bytearray)) else val
    if isinstance(sd, dict):  # kształt alternatywny (starsze wersje)
        val = sd.get(did)
        if val is None and len(sd) == 1:
            val = next(iter(sd.values()))
        if val is not None:
            return bytes(val) if isinstance(val, (bytes, bytearray)) else val
    data = bytes(r.data) if getattr(r, "data", None) else b""
    echo = bytes([(did >> 8) & 0xFF, did & 0xFF])
    if len(data) >= 2 and data[:2] == echo:
        data = data[2:]
    return data


def fmt_bytes(data: bytes) -> str:
    """Hex + czytelny ASCII (gdy coś drukowalne)."""
    if data is None:
        return "-"
    hexs = " ".join(f"{b:02X}" for b in data)
    text = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    if any(32 <= b < 127 for b in data):
        return f'{hexs}  "{text}"'
    return hexs


def fmt_dtc(dtc) -> str:
    """DTC z udsoncan -> '0x123456  status=0x24 (test_failed, confirmed)'."""
    status = getattr(dtc, "status", None)
    flags = []
    if status is not None:
        for attr, label in (
            ("test_failed", "test_failed"),
            ("test_failed_this_operation_cycle", "failed_this_cycle"),
            ("pending", "pending"),
            ("confirmed", "confirmed"),
            ("test_not_completed_since_last_clear", "not_completed"),
            ("test_failed_since_last_clear", "failed_since_clear"),
            ("warning_indicator_requested", "warning_lamp"),
        ):
            if getattr(status, attr, False):
                flags.append(label)
        try:
            raw = int(status.get_byte_as_int())
        except Exception:  # noqa: BLE001
            raw = None
    else:
        raw = None
    marker = f"status=0x{raw:02X}" if raw is not None else "status=?"
    info = f" ({', '.join(flags)})" if flags else ""
    return f"0x{dtc.id:06X}  {marker}{info}"


# ---------------------------------------------------------------------------
# Log sesji
# ---------------------------------------------------------------------------

class UdsLog:
    """Prosty log tekstowy: >> wysłane, << odebrane, # notatki."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a", encoding="utf-8")

    def _line(self, tag: str, text: str) -> None:
        stamp = time.strftime("%H:%M:%S") + f".{int(time.time() % 1 * 1000):03d}"
        self._fh.write(f"[{stamp}] {tag} {text}\n")
        self._fh.flush()

    def tx(self, payload: bytes) -> None:
        self._line(">>", payload.hex(" ").upper())

    def rx(self, payload: bytes) -> None:
        self._line("<<", payload.hex(" ").upper())

    def note(self, text: str) -> None:
        self._line("#", text)

    def scan_line(self, text: str) -> None:
        self._line("scan", text)

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:  # noqa: BLE001
            pass


def open_log(prefix: str = "uds") -> UdsLog:
    """Nowy log w ``logs/`` z datą i godziną (np. ``logs/uds_20261007_0102.log``)."""
    from .config import LOGS_DIR

    stamp = time.strftime("%Y%m%d_%H%M%S")
    return UdsLog(Path(LOGS_DIR) / f"{prefix}_{stamp}.log")


# ---------------------------------------------------------------------------
# Skaner ECU (pojedyncze ramki ISO-TP, bez stosu)
# ---------------------------------------------------------------------------

def make_single_frame(payload: bytes, pad: int = 0x00) -> bytes:
    """ISO-TP Single Frame + dopełnienie do 8 bajtów."""
    n = len(payload)
    if n > 7:
        raise ValueError("payload > 7 bajtów nie mieści się w Single Frame")
    return bytes([n]) + bytes(payload) + bytes([pad]) * (7 - n)


def _parse_sf(data: bytes):
    """(payload) jeśli ramka wygląda jak ISO-TP Single Frame, inaczej None."""
    if len(data) < 2:
        return None
    if (data[0] & 0xF0) != 0x00:
        return None
    ln = data[0] & 0x0F
    if 0 < ln <= 7 and ln <= len(data) - 1:
        return bytes(data[1:1 + ln])
    return None


def scan_ecus(bus, ids, offset: int = 8, probe: bytes = b"",
              timeout: float = 0.05, extended: bool = False,
              any_response: bool = True, on_progress=None, on_result=None,
              log: UdsLog | None = None):
    """Skanuje listę ID żądań; zbiera odpowiedzi spod ``id+offset`` (i inne, opcjonalnie).

    Zwraca listę dictów: ``{txid, rxid, resp, others}``
    (``resp`` = payload ISO-TP albo None; ``others`` = [(can_id, payload), ...]).
    """
    if not probe:
        probe = b"\x3E\x00"  # TesterPresent
    frame = make_single_frame(probe)
    results = []
    total = len(ids)
    for i, txid in enumerate(ids, 1):
        rxid = txid + offset
        # opróżnij bufor, żeby nie złapać starej odpowiedzi
        while bus.recv(timeout=0) is not None:
            pass
        bus.send(can.Message(arbitration_id=txid, is_extended_id=extended, data=frame))
        deadline = time.monotonic() + timeout
        hit = None
        others = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            msg = bus.recv(timeout=remaining)
            if msg is None:
                break
            if msg.arbitration_id == rxid and bool(msg.is_extended_id) == extended:
                hit = msg
                break
            if any_response:
                payload = _parse_sf(bytes(msg.data))
                if payload is not None:
                    others.append((msg.arbitration_id, payload))
        res = {
            "txid": txid,
            "rxid": rxid,
            "resp": _parse_sf(bytes(hit.data)) if hit is not None else None,
            "others": others,
        }
        results.append(res)
        if log is not None:
            main = " ".join(f"{b:02X}" for b in res["resp"]) if res["resp"] else "brak"
            log.scan_line(f"0x{txid:03X} -> 0x{rxid:03X}: {main}")
        if on_result is not None and (res["resp"] is not None or others):
            on_result(res)
        if on_progress is not None:
            on_progress(i, total)
    return results
