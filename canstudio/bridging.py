"""Silnik "man in the middle" (bridge) dla CAN.

Przekazywanie ramek między dwoma kanałami (A -> B, B -> A) z możliwością:
* filtrowania (pass/drop) wybranych ID,
* modyfikacji bajtów w locie (``set``),
* automatycznego prowadzenia liczników (``counter``),
* automatycznego przeliczania sum kontrolnych (``checksum``, algorytmy z
  ``canstudio.checksums``),
* trybu ``tap`` (tylko podgląd i logowanie, bez przekazywania).

Wymaga DWÓCH interfejsów CAN (np. dwa Canable) - na jednym kanale fizyczny
MITM nie istnieje. Całość jest testowalna bez sprzętu na magistralach
wirtualnych (``demo_virtual``).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import can

from .checksums import compute as checksum_compute
from .frames import format_frame, parse_id


def _parse_id_ref(value) -> int:
    if isinstance(value, int):
        return value
    return parse_id(str(value))


# ---------------------------------------------------------------------------
# Pomocnicze: adresy kanałów (używane przez CLI i GUI)
# ---------------------------------------------------------------------------

class EndpointArgs:
    """Minimalny shim argumentów dla ``canstudio.bus.open_bus``."""


def make_endpoint_args(interface: str, channel: str, bitrate: int,
                       tty_baud: int = 115200, silent: bool = False) -> EndpointArgs:
    ep = EndpointArgs()
    ep.interface = interface
    ep.channel = channel
    ep.bitrate = bitrate
    ep.tty_baud = tty_baud
    ep.silent = silent          # bridge MUSI działać w trybie normalnym (ACK)
    ep.silent_mode = "m1"
    ep.fd = False
    return ep


def parse_endpoint(spec: str) -> tuple:
    """'slcan:COM7' -> ('slcan', 'COM7'); 'COM7' -> ('slcan', 'COM7')."""
    if ":" in spec:
        iface, _, channel = spec.partition(":")
        return iface, channel
    return "slcan", spec


@dataclass
class SetRule:
    arbitration_id: int
    byte: int
    value: int


@dataclass
class CounterRule:
    arbitration_id: int
    byte: int


@dataclass
class ChecksumRule:
    arbitration_id: int
    byte: int
    algo: str


@dataclass
class BridgeRules:
    drop_ids: set = field(default_factory=set)
    set_rules: list = field(default_factory=list)
    counter_rules: list = field(default_factory=list)
    checksum_rules: list = field(default_factory=list)
    tap: bool = False

    @staticmethod
    def from_mapping(data: dict) -> "BridgeRules":
        rules = BridgeRules()
        rules.drop_ids = {_parse_id_ref(x) for x in data.get("drop", [])}
        for item in data.get("set", []):
            rules.set_rules.append(SetRule(_parse_id_ref(item["id"]), int(item["byte"]),
                                           _parse_id_ref(item["value"])))
        for item in data.get("counter", []):
            rules.counter_rules.append(CounterRule(_parse_id_ref(item["id"]), int(item["byte"])))
        for item in data.get("checksum", []):
            rules.checksum_rules.append(ChecksumRule(_parse_id_ref(item["id"]), int(item["byte"]),
                                                     str(item["algo"])))
        return rules


class BridgeState:
    """Stan per kierunek (liczniki rosną niezależnie w każdej stronę)."""

    def __init__(self):
        self.counters: dict = {}


def parse_set_spec(spec: str) -> SetRule:
    """'ID:BYTE=VALUE' -> SetRule (wspólne dla bridge/replay)."""
    left, _, value = spec.partition("=")
    arb, _, byte = left.partition(":")
    return SetRule(_parse_id_ref(arb), int(byte), _parse_id_ref(value))


def parse_counter_spec(spec: str) -> CounterRule:
    """'ID:BYTE' -> CounterRule."""
    arb, _, byte = spec.partition(":")
    return CounterRule(_parse_id_ref(arb), int(byte))


def parse_checksum_spec(spec: str) -> ChecksumRule:
    """'ID:BYTE:ALGO' -> ChecksumRule."""
    arb, _, rest = spec.partition(":")
    byte, _, algo = rest.partition(":")
    return ChecksumRule(_parse_id_ref(arb), int(byte), algo)


def transform(data: bytes, arbitration_id: int, rules: BridgeRules, state: BridgeState,
              direction: str) -> tuple:
    """Zwraca (nowe_bajty, czy_zmodyfikowano)."""
    d = bytearray(data)
    modified = False

    for rule in rules.set_rules:
        if rule.arbitration_id == arbitration_id and rule.byte < len(d):
            if d[rule.byte] != rule.value:
                modified = True
            d[rule.byte] = rule.value

    for rule in rules.counter_rules:
        if rule.arbitration_id == arbitration_id and rule.byte < len(d):
            key = (direction, arbitration_id)
            current = state.counters.get(key)
            new = d[rule.byte] if current is None else (current + 1) & 0xFF
            if d[rule.byte] != new:
                modified = True
            d[rule.byte] = new
            state.counters[key] = new

    for rule in rules.checksum_rules:
        if rule.arbitration_id == arbitration_id and rule.byte < len(d):
            others = bytes(x for i, x in enumerate(d) if i != rule.byte)
            try:
                value = checksum_compute(rule.algo, others)
            except KeyError:
                continue
            if d[rule.byte] != value:
                modified = True
            d[rule.byte] = value

    return bytes(d), modified


class BridgeLogger:
    """Zapis przekazanych ramek do logu (candump) - bezpieczny wątkowo."""

    def __init__(self, path):
        self.fh = open(path, "w", encoding="utf-8", buffering=1)
        self.lock = threading.Lock()

    def line(self, msg: can.Message, channel: str, modified: bool = False) -> None:
        with self.lock:
            tag = channel + ("*" if modified else "")
            self.fh.write(format_frame(msg, tag) + "\n")

    def close(self) -> None:
        try:
            self.fh.close()
        except Exception:
            pass


def run_bridge(bus_in, bus_out, rules: BridgeRules, direction: str = "A>B",
               logger: Optional["BridgeLogger"] = None,
               stop_event: Optional[threading.Event] = None,
               timeout: float = 0.05, stats: Optional[dict] = None) -> None:
    """Pętla przekazywania: ramki z ``bus_in`` -> ``bus_out``."""
    if stats is None:
        stats = {}
    stats.setdefault("fwd", 0)
    stats.setdefault("mod", 0)
    stats.setdefault("dropped", 0)
    state = BridgeState()

    while not (stop_event and stop_event.is_set()):
        msg = bus_in.recv(timeout=timeout)
        if msg is None:
            continue

        if rules.tap:
            if logger:
                logger.line(msg, direction, modified=False)
            stats["fwd"] += 1
            continue

        if msg.arbitration_id in rules.drop_ids:
            stats["dropped"] += 1
            continue

        try:
            new_data, modified = transform(bytes(msg.data), msg.arbitration_id,
                                           rules, state, direction)
        except Exception:
            new_data, modified = bytes(msg.data), False

        out_msg = can.Message(
            arbitration_id=msg.arbitration_id,
            is_extended_id=msg.is_extended_id,
            data=new_data,
            is_remote_frame=msg.is_remote_frame,
        )
        try:
            bus_out.send(out_msg)
            stats["fwd"] += 1
            if modified:
                stats["mod"] += 1
        except Exception:
            stats["errors"] = stats.get("errors", 0) + 1
            continue

        if logger:
            logger.line(out_msg, direction, modified=modified)


def demo_virtual(verbose: bool = True) -> bool:
    """Demo/self-test MITM na magistralach wirtualnych (bez sprzętu).

    Sprawdza: przekazywanie, ustawianie bajtu, prowadzenie licznika i
    przeliczanie sumy kontrolnej (xor8).
    """
    chin, chout = "mitm-in", "mitm-out"
    sender = can.Bus(interface="virtual", channel=chin)
    bridge_in = can.Bus(interface="virtual", channel=chin)
    bridge_out = can.Bus(interface="virtual", channel=chout)
    reader = can.Bus(interface="virtual", channel=chout)

    rules = BridgeRules(
        set_rules=[SetRule(0x130, 3, 0x2A)],
        counter_rules=[CounterRule(0x130, 1)],
        checksum_rules=[ChecksumRule(0x130, 7, "xor8")],
    )
    stop = threading.Event()
    stats = {"fwd": 0, "mod": 0}
    thread = threading.Thread(
        target=run_bridge,
        args=(bridge_in, bridge_out, rules, "demo", None, stop, 0.02, stats),
        daemon=True,
    )
    thread.start()

    sent = []
    try:
        for i in range(5):
            body = bytearray([0x03, i * 3, 0x10, 0x00, 0x80, 0x00, 0x00, 0x00])
            chk = 0
            for x in range(7):
                chk ^= body[x]
            body[7] = chk
            sent.append(bytes(body))
            sender.send(can.Message(arbitration_id=0x130, data=bytes(body), is_extended_id=False))
            time.sleep(0.03)

        got = []
        t_end = time.time() + 2.0
        while time.time() < t_end and len(got) < 5:
            msg = reader.recv(timeout=0.2)
            if msg is not None:
                got.append(bytes(msg.data))
    finally:
        stop.set()
        thread.join(timeout=1.0)
        for bus in (sender, bridge_in, bridge_out, reader):
            bus.shutdown()

    ok = len(got) == 5
    if ok:
        for old, new in zip(sent, got):
            if new[3] != 0x2A:
                ok = False
            chk = 0
            for x in range(7):
                chk ^= new[x]
            if new[7] != chk:
                ok = False
        counters = [g[1] for g in got]
        expected = [counters[0]] + [(counters[i - 1] + 1) & 0xFF for i in range(1, 5)]
        if counters != expected:
            ok = False

    if verbose:
        print("# demo MITM na magistralach wirtualnych:")
        for old, new in zip(sent, got):
            flag = "*" if old != new else " "
            print(f"  IN {old.hex(' ').upper()}  {flag}->  OUT {new.hex(' ').upper()}")
        print(f"  przekazano={stats['fwd']} zmodyfikowano={stats['mod']}"
              f"  ->  {'PASS' if ok else 'FAIL'}")
    return ok
