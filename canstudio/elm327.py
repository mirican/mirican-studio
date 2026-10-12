"""elm327.py - sterownik adaptera ELM327 (vLinker MS i klony) po porcie szeregowym.

Warstwa transportowa: komendy AT/OBD po linii tekstowej, odpowiedzi do promptu '>'.
Warstwa OBD (PID-y, DTC, VIN) jest w ``canstudio.obd``.

Uwaga: to NIE jest interfejs do nasluchu magistrali CAN (ELM327 nie robi
pelnego sniffu jak Canable). Sluzy do diagnostyki OBD-II: PID-y (tryb 01),
DTC (03/04), VIN (09 02) itd.

vLinker MS na PC: klasyczny BT -> "Standardowy port szeregowy przez link
Bluetooth (COMx)"; np. COM8, baud 115200.
"""

from __future__ import annotations

import time

try:
    import serial
    from serial.tools import list_ports
except Exception:  # noqa: BLE001 - brak pyserial: reszta toolkitu dziala dalej
    serial = None
    list_ports = None

DEFAULT_BAUD = 115200
PROMPT = ">"

#: opcjonalny MAC konkretnego egzemplarza (prywatny; wpisz u siebie, np. "aabbccddeeff")
VLINKER_MAC = ""
#: Vgate VID/PID widziane w hwid portu BT SPP (VID&0001005E_PID&0001)
VGATE_VID_PID = "vid&0001005e_pid&0001"


def serial_available() -> bool:
    """Czy pyserial jest dostepny (inaczej narzedzie obd nie zadziala)."""
    return serial is not None


def find_elm_port():
    """Szuka portu adaptera ELM327 (typowo vLinker MS).

    Zwraca ``(port, powod)`` albo ``(None, None)``. Kolejnosc kryteriow:
    MAC naszego vLinkera > nazwa "vLinker" > VID/PID Vgate.
    """
    if list_ports is None:
        return None, None
    best = (0, None, None)
    for p in list_ports.comports():
        text = f"{p.device} {p.hwid} {p.description}".lower()
        if VLINKER_MAC and VLINKER_MAC in text:
            cand = (3, p.device, "MAC vLinker MS")
        elif "vlinker" in text:
            cand = (2, p.device, "nazwa 'vLinker'")
        elif VGATE_VID_PID in text:
            cand = (1, p.device, "VID/PID Vgate")
        else:
            continue
        if cand[0] > best[0]:
            best = cand
    return best[1], best[2]


def clean_response(text: str, cmd: str) -> str:
    """Normalizuje odpowiedz ELM: CR->LF, usuwa echo komendy i prompt '>'."""
    lines = []
    for raw in text.replace("\r", "\n").split("\n"):
        s = raw.strip()
        if not s or s == PROMPT:
            continue
        if s.upper() == cmd.strip().upper():
            continue  # echo komendy (gdy ATE0 jeszcze nie zadzialalo)
        lines.append(s)
    return "\n".join(lines)


class Elm327:
    """Klient ELM327 po porcie szeregowym (BT SPP albo USB).

    ``opener`` - opcjonalna funkcja otwierajaca port (do testow syntetycznych).
    """

    def __init__(self, port: str, baud: int = DEFAULT_BAUD, timeout: float = 3.0,
                 opener=None):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self._opener = opener
        self._ser = None
        self.history: list = []

    # -- polaczenie -----------------------------------------------------
    def open(self, attempts: int = 3, delay: float = 2.0) -> None:
        """Otwiera port (z ponowieniami - BT potrafi wymagac chwili na dial)."""
        if serial is None and self._opener is None:
            raise RuntimeError("Brak pyserial (py -m pip install pyserial)")
        last = None
        for _ in range(attempts):
            try:
                if self._opener is not None:
                    self._ser = self._opener()
                else:
                    self._ser = serial.Serial(self.port, self.baud,
                                              timeout=0.05, write_timeout=3.0)
                return
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(delay)
        raise ConnectionError(f"Nie moge otworzyc {self.port}: {last}")

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:  # noqa: BLE001
                pass
            self._ser = None

    @property
    def is_open(self) -> bool:
        return self._ser is not None

    # -- komendy ---------------------------------------------------------
    def cmd(self, cmd: str, timeout: float | None = None) -> str:
        """Wysyla komende (CR na koncu), czeka na prompt. Zwraca oczyszczony tekst."""
        if self._ser is None:
            raise RuntimeError("port nie otwarty")
        timeout = self.timeout if timeout is None else timeout
        try:
            self._ser.reset_input_buffer()
        except Exception:  # noqa: BLE001
            pass
        self._ser.write((cmd + "\r").encode("ascii", "replace"))
        try:
            self._ser.flush()
        except Exception:  # noqa: BLE001
            pass
        t0 = time.monotonic()
        buf = b""
        while (time.monotonic() - t0) < timeout:
            chunk = self._ser.read(256)
            if chunk:
                buf += chunk
                if PROMPT.encode() in buf:
                    break
            else:
                time.sleep(0.005)
        text = buf.decode("ascii", "replace")
        self.history.append((cmd, text))
        return clean_response(text, cmd)

    def init(self) -> dict:
        """Sekwencja startowa; zwraca {adapter, voltage} (teksty z ATI/ATRV)."""
        self.cmd("ATZ", timeout=8.0)
        for c in ("ATE0", "ATL0", "ATS1", "ATH1", "ATAT1", "ATSP0"):
            self.cmd(c)
        return {"adapter": self.cmd("ATI"), "voltage": self.cmd("ATRV")}

    def probe_bus(self, timeout: float = 15.0) -> dict:
        """Probe 0100: czy ECU odpowiada na magistrali (wymaga zaplonu)."""
        raw = self.cmd("0100", timeout=timeout)
        compact = raw.replace(" ", "")
        up = "4100" in compact and "UNABLETOCONNECT" not in raw.replace(" ", "").upper()
        return {"bus": up, "raw": raw}

    def obd(self, svc_pid: str, timeout: float | None = None) -> str:
        """Zadanie OBD (np. '010C'); zwraca surowy tekst odpowiedzi."""
        return self.cmd(svc_pid, timeout=timeout)
