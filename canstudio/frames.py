"""Model ramki i konwersje formatów (candump)."""

from __future__ import annotations

import re
from dataclasses import dataclass

import can


@dataclass
class Frame:
    """Pojedyncza ramka z logu (format candump)."""

    timestamp: float
    channel: str
    arbitration_id: int
    is_extended: bool
    data: bytes
    is_remote: bool = False


def frame_from_message(msg: can.Message, channel: str) -> Frame:
    return Frame(
        timestamp=msg.timestamp,
        channel=channel,
        arbitration_id=msg.arbitration_id,
        is_extended=msg.is_extended_id,
        data=bytes(msg.data),
        is_remote=msg.is_remote_frame,
    )


def format_frame(msg: can.Message, channel: str) -> str:
    """Format ramki w stylu ``candump -L``: (czas) kanał ID#DANE."""
    sid = f"{msg.arbitration_id:08X}" if msg.is_extended_id else f"{msg.arbitration_id:03X}"
    if msg.is_remote_frame:
        payload = "R"
    else:
        payload = bytes(msg.data).hex().upper()
    return f"({msg.timestamp:.6f}) {channel} {sid}#{payload}"


_LINE_RE = re.compile(
    r"^\((?P<ts>[\d.]+)\)\s+(?P<ch>\S+)\s+(?P<id>[0-9A-Fa-f]{1,8})#(?P<data>[0-9A-Fa-f]*|R)$"
)


def parse_frame_line(line: str) -> Frame:
    """Parsuje linię logu w formacie candump / candump -L."""
    m = _LINE_RE.match(line.strip())
    if not m:
        raise ValueError(f"Nie mogę sparsować linii: {line!r}")
    sid = m.group("id")
    sdata = m.group("data")
    remote = sdata.upper() == "R"
    data = b"" if (remote or not sdata) else bytes.fromhex(sdata)
    return Frame(
        timestamp=float(m.group("ts")),
        channel=m.group("ch"),
        arbitration_id=int(sid, 16),
        is_extended=len(sid) > 3,
        data=data,
        is_remote=remote,
    )


def message_from_frame(frame: Frame, with_meta: bool = True) -> can.Message:
    """Zamienia ramkę z logu na ``can.Message`` (do wysyłki / konwersji)."""
    msg = can.Message(
        arbitration_id=frame.arbitration_id,
        is_extended_id=frame.is_extended,
        data=frame.data,
        is_remote_frame=frame.is_remote,
    )
    if with_meta:
        msg.timestamp = frame.timestamp
        if frame.channel:
            msg.channel = frame.channel
    return msg


def parse_id(text: str) -> int:
    """'0x123' / '123' / '18DAF110' -> int (litery a-f oznaczają hex)."""
    s = text.strip().lower()
    if s.startswith("0x"):
        return int(s, 16)
    if any(c in "abcdef" for c in s):
        return int(s, 16)
    return int(s, 0)


def parse_ids(text: str) -> set:
    """'0x123, 456' -> {291, 456}."""
    return {parse_id(x) for x in text.replace(";", ",").split(",") if x.strip()}
