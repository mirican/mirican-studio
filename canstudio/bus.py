"""Wybór i otwieranie magistrali CAN.

Każdy interfejs rejestruje się w ``_BUILDERS`` przez dekorator ``@bus_factory``.
Aby dodać nowy interfejs: napisz funkcję budującą obiekt ``can.BusABC``
i ozdób ją ``@bus_factory("nazwa")`` - pojawi się automatycznie w CLI
(opcja ``--interface``) we wszystkich narzędziach.
"""

from __future__ import annotations

import argparse
import sys

import can

try:
    from can.interfaces.slcan import slcanBus as _SlcanBus
except Exception:  # np. brak pyserial
    _SlcanBus = None


if _SlcanBus is not None:

    class Canable2SlcanBus(_SlcanBus):  # type: ignore[misc]
        """slcanBus z trybem silent opartym o komendę ``M1`` (firmware canable2).

        Firmware normaldotcom/canable2 (m.in. MKS CANable 2.0 PRO) nie obsługuje
        standardowej komendy ``L`` - tryb nasłuchu włącza ``M1`` wysyłane
        przed komendą ``O`` otwierającą kanał.
        """

        def __init__(self, *args, silent_m1: bool = False, **kwargs):
            # ustawiane przed super().__init__, bo konstruktor woła self.open()
            self._silent_m1 = silent_m1
            super().__init__(*args, **kwargs)

        def open(self) -> None:  # noqa: A003 - zgodność z API python-can
            if self._silent_m1:
                self._write("M1")
                self._write("O")
            else:
                super().open()

else:
    Canable2SlcanBus = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Rejestr interfejsów
# ---------------------------------------------------------------------------

_BUILDERS: dict = {}


def bus_factory(name: str):
    """Dekorator rejestrujący funkcję budującą magistralę pod daną nazwą."""

    def _decorator(fn):
        _BUILDERS[name] = fn
        return fn

    return _decorator


@bus_factory("slcan")
def _build_slcan(args):
    kwargs = dict(
        channel=args.channel,
        bitrate=args.bitrate or 500000,
        tty_baudrate=getattr(args, "tty_baud", 115200),
    )
    silent = bool(getattr(args, "silent", False))
    mode = getattr(args, "silent_mode", "m1")
    if silent and mode == "m1" and Canable2SlcanBus is not None:
        return Canable2SlcanBus(silent_m1=True, **kwargs)
    if silent:
        kwargs["listen_only"] = True
    return can.Bus(interface="slcan", **kwargs)


@bus_factory("gs_usb")
def _build_gs_usb(args):
    return can.Bus(interface="gs_usb", channel=args.channel, bitrate=args.bitrate or 500000)


@bus_factory("pcan")
def _build_pcan(args):
    return can.Bus(interface="pcan", channel=args.channel, bitrate=args.bitrate or 500000)


@bus_factory("virtual")
def _build_virtual(args):
    return can.Bus(interface="virtual", channel=args.channel or "vcan0")


@bus_factory("socketcan")
def _build_socketcan(args):
    kwargs = dict(channel=args.channel)
    if args.bitrate:
        kwargs["bitrate"] = args.bitrate
    return can.Bus(interface="socketcan", **kwargs)


INTERFACES = tuple(_BUILDERS)


# ---------------------------------------------------------------------------
# Wspólne argumenty CLI i otwieranie
# ---------------------------------------------------------------------------

def add_bus_args(parser: argparse.ArgumentParser) -> None:
    """Dodaje wspólne argumenty wyboru magistrali do parsera."""
    g = parser.add_argument_group("magistrala CAN")
    g.add_argument("--interface", "-i", default="slcan", choices=INTERFACES,
                   help="slcan = Canable/MKS po USB (domyślne); gs_usb = candleLight; "
                        "pcan = PEAK; virtual = test bez sprzętu; socketcan = Linux")
    g.add_argument("--channel", "-c", default=None,
                   help="slcan: COMx (np. COM7) / /dev/ttyACM0; gs_usb: numer urządzenia; "
                        "pcan: np. PCAN_USBBUS1; socketcan/virtual: nazwa kanału")
    g.add_argument("--bitrate", "-b", type=int, default=None,
                   help="prędkość magistrali w bit/s (domyślnie 500000 lub wartość z --profile)")
    g.add_argument("--tty-baud", type=int, default=115200,
                   help="prędkość portu COM dla slcan (dla CDC zwykle bez znaczenia)")
    g.add_argument("--silent", action="store_true",
                   help="nasłuch bierny (bez ACK): canable2 = M1, inne firmware = L")
    g.add_argument("--silent-mode", choices=("m1", "l"), default="m1",
                   help="sposób włączania silent dla slcan (domyślnie M1 = canable2)")
    g.add_argument("--fd", action="store_true", help="użyj CAN FD (jeśli sprzęt obsługuje)")


def open_bus(args):
    """Tworzy i zwraca otwartą magistralę na podstawie argumentów CLI."""
    iface = getattr(args, "interface", "slcan")
    if iface not in _BUILDERS:
        sys.exit(f"Nieznany interfejs: {iface} (dostępne: {', '.join(INTERFACES)})")
    if iface != "virtual" and not getattr(args, "channel", None):
        sys.exit(f"Błąd: dla interfejsu '{iface}' podaj --channel (np. --channel COM7)")
    return _BUILDERS[iface](args)


def serial_ports():
    """Lista portów szeregowych (pyserial)."""
    from serial.tools import list_ports
    return list(list_ports.comports())
