"""Narzędzie: selftest — testy canstudio bez samochodu (+ opcjonalnie sprzęt)."""

from __future__ import annotations

import argparse
import time

import can

from ..bridging import demo_virtual
from ..bus import Canable2SlcanBus
from ..checksums import analyze_frames
from ..config import ROOT
from ..dbc import load_dbc
from ..detect import ChangeDetector, classify_frames
from ..diffing import diff_logs
from ..frames import format_frame, parse_frame_line
from ..markers import Marker, correlate

NAME = "selftest"
HELP = "Testy canstudio (offline; --port COMx do testu sprzętowego)"


def test_format() -> None:
    msg = can.Message(arbitration_id=0x123,
                      is_extended_id=False,
                      data=bytes.fromhex("DEADBEEF01020304"),
                      timestamp=1234.56789)
    line = format_frame(msg, "can0")
    assert line.startswith("(1234.567890) can0 123#DEADBEEF01020304"), line
    frame = parse_frame_line(line)
    assert frame.arbitration_id == 0x123 and not frame.is_extended
    assert frame.data == bytes.fromhex("DEADBEEF01020304")

    msg_ext = can.Message(arbitration_id=0x18DAF110, data=b"\x01\x02",
                          is_extended_id=True, timestamp=1.0)
    frame_ext = parse_frame_line(format_frame(msg_ext, "can0"))
    assert frame_ext.arbitration_id == 0x18DAF110 and frame_ext.is_extended
    print("[OK] format / parse candump")


def test_dbc() -> None:
    db = load_dbc(ROOT / "dbc" / "example.dbc")
    encoder = db.get_message_by_frame_id(0x123)
    data = encoder.encode({"EngineSpeed": 2000.0, "ThrottlePos": 50.0,
                           "CoolantTemp": 90.0, "VehicleSpeed": 100.0})
    decoded = db.decode_message(0x123, data)
    assert abs(decoded["EngineSpeed"] - 2000.0) < 1.0, decoded
    assert abs(decoded["VehicleSpeed"] - 100.0) < 0.1, decoded
    pretty = {k: round(v, 2) if isinstance(v, float) else v for k, v in decoded.items()}
    print("[OK] DBC:", pretty)


def test_virtual() -> None:
    rx = can.Bus(interface="virtual", channel="selftest")
    tx = can.Bus(interface="virtual", channel="selftest")
    try:
        tx.send(can.Message(arbitration_id=0x321,
                            is_extended_id=False,
                            data=bytes.fromhex("1122334455667788"),
                            timestamp=1.0))
        got = rx.recv(timeout=2.0)
        assert got is not None and got.arbitration_id == 0x321
        assert bytes(got.data) == bytes.fromhex("1122334455667788")
    finally:
        rx.shutdown()
        tx.shutdown()
    print("[OK] pętla wirtualna")


def test_analysis() -> None:
    frames = []
    for i in range(128):
        body = [0x03, i & 0xFF, 0x10, i % 5, 0x80, 0x00, 0x00]
        checksum = 0
        for x in body:
            checksum ^= x
        frames.append(bytes(body + [checksum]))
    result = analyze_frames(frames)
    assert result.count == 128, result
    assert any(c.byte == 1 for c in result.counters), result.counters
    assert any(h.byte == -1 and h.algo.startswith("xor8") and h.score > 0.99
               for h in result.checksums), result.checksums
    print("[OK] detekcja licznika + sumy kontrolnej (xor8)")


def test_detect() -> None:
    detector = ChangeDetector(min_stable=10, min_gap_s=0.0)
    events = []
    for i in range(50):
        events += detector.feed(0x2CA, bytes([0x00, i & 0xFF]), i * 0.01)
    for i in range(50, 60):
        events += detector.feed(0x2CA, bytes([0x01, i & 0xFF]), i * 0.01)
    assert any(e.byte == 0 and e.new == 1 for e in events), events
    assert all(e.byte != 1 for e in events if e.byte >= 0), events

    frames = []
    for i in range(60):
        body = [0x03, i & 0xFF, 0x00 if i < 30 else 0x01, (i * 7) % 200,
                0x80, 0x00, 0x00, 0]
        chk = 0
        for x in range(7):
            chk ^= body[x]
        body[7] = chk
        frames.append(bytes(body))
    classes = {c.byte: c for c in classify_frames(frames)}
    assert classes[0].kind == "stały", classes[0]
    assert classes[1].kind == "licznik", classes[1]
    assert classes[2].kind.startswith("przełącznik"), classes[2]
    assert classes[3].kind == "sensor", classes[3]
    assert classes[7].kind == "suma", classes[7]
    print("[OK] detekcja zmian + klasyfikacja bajtów")


def test_diff() -> None:
    class FakeMsg:
        def __init__(self, aid, data):
            self.arbitration_id = aid
            self.data = data

    a = [FakeMsg(0x130, bytes([1, 2, 3, i % 5])) for i in range(30)]
    b = [FakeMsg(0x130, bytes([1, 2, 90 + i % 5, i % 5])) for i in range(30)]
    b += [FakeMsg(0x1A0, bytes([9, 9])) for _ in range(30)]
    diffs, only = diff_logs(a, b, min_frames=10)
    assert diffs and diffs[0].arbitration_id == 0x130, diffs
    assert any(bd.byte == 2 for bd in diffs[0].bytes), diffs[0].bytes
    assert any(aid == 0x1A0 for aid, _ in only["B"]), only
    print("[OK] porównywanie logów (diff)")


def test_correlate() -> None:
    marks = [Marker(1000.0 + 1.53 + k * 4.0, "przycisk 1") for k in range(5)]
    messages = []
    for i in range(400):
        t = 1000.0 + i * 0.05
        pressed = any(mk.timestamp <= t <= mk.timestamp + 0.6 for mk in marks)
        data = bytearray([0x11, 0x22, 1 if pressed else 0, 0x00])
        messages.append(can.Message(arbitration_id=0x2CA, is_extended_id=False,
                                    data=bytes(data), timestamp=t))
    # rzadki szum w b3, częściowo przypadkiem w oknach znaczników
    for k in (37, 151, 289):
        data = bytearray(messages[k].data)
        data[3] = 0x77
        messages[k] = can.Message(arbitration_id=0x2CA, is_extended_id=False,
                                  data=bytes(data), timestamp=messages[k].timestamp)

    report = correlate(messages, marks, window_s=1.0, top=5)
    count, cands = report["przycisk 1"]
    assert count == 5, count
    assert cands and cands[0].arbitration_id == 0x2CA and cands[0].byte == 2, cands
    assert cands[0].hits == 5, cands[0]
    print("[OK] korelacja znaczników (przycisk -> bajt)")


def test_bridge() -> None:
    assert demo_virtual(verbose=False), "demo MITM nie przeszło"
    print("[OK] bridge / MITM (magistrala wirtualna)")


def test_dbc_library() -> None:
    """Sprawdza, że wszystkie lokalne bazy DBC wczytują się (poza znanymi wyjątkami opendbc)."""
    dbc_dir = ROOT / "dbc"
    ok, essential_bad, loose_bad = 0, [], []
    for f in sorted(dbc_dir.rglob("*.dbc")):
        rel = f.relative_to(dbc_dir)
        top = rel.parts[0] if len(rel.parts) > 1 else ""
        try:
            load_dbc(f)
            ok += 1
        except Exception:  # noqa: BLE001
            if top == "opendbc":
                loose_bad.append(f.name)
            else:
                essential_bad.append(f.name)
    assert not essential_bad, f"nie wczytują się: {essential_bad}"
    extra = f", opendbc pominięte: {len(loose_bad)}" if loose_bad else ""
    print(f"[OK] biblioteka DBC: {ok} plików OK{extra}")


def test_hardware(port: str) -> None:
    bus = Canable2SlcanBus(channel=port, bitrate=500000, tty_baudrate=115200)
    try:
        version = None
        try:
            bus._write("V")
            version = bus._read(timeout=1.0)
        except Exception:
            pass
        print(f"[OK] otwarto {port}; firmware: {version!r}")
        t_end = time.monotonic() + 3.0
        count = 0
        while time.monotonic() < t_end:
            if bus.recv(timeout=0.5) is not None:
                count += 1
        print(f"[OK] 3 s nasłuchu; odebranych ramek: {count}")
    finally:
        bus.shutdown()


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--port", help="port COM Canable do testu sprzętowego (np. COM7)")


def run(args) -> int:
    test_format()
    test_dbc()
    test_dbc_library()
    test_virtual()
    test_analysis()
    test_detect()
    test_diff()
    test_correlate()
    test_bridge()
    if args.port:
        test_hardware(args.port)
    print("SELFTEST PASS")
    return 0
