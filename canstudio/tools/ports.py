"""Narzędzie: ports — lista portów szeregowych."""

from __future__ import annotations

import argparse

from ..bus import serial_ports
from ..json_cli import add_json_args, emit, json_mode

NAME = "ports"
HELP = "Lista portów szeregowych (COM) z VID:PID"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    add_json_args(parser)


def run(args) -> int:
    json_mode(args)
    ports = serial_ports()
    items = [{"device": p.device,
              "vid_pid": f"{p.vid:04X}:{p.pid:04X}" if p.vid else None,
              "desc": p.description or "",
              "canable": bool(p.vid == 0x16D0 and p.pid == 0x117E)} for p in ports]
    if getattr(args, "json", False):
        emit({"ok": True, "ports": items})
        return 0
    if not ports:
        print("Brak portów szeregowych.")
        return 0
    for port in ports:
        vidpid = f"{port.vid:04X}:{port.pid:04X}" if port.vid else "-"
        print(f"{port.device:10s}  {vidpid:10s}  {port.description}")
    return 0
