"""Serwer CAN Studio GUI (FastAPI + WebSocket).

* ``GET /``            - interfejs (index.html),
* ``/api/*``           - REST (porty, connect, send, record, mark, dbc, insight, uds),
* ``/ws``              - strumień na żywo (ramki + zdarzenia + statystyki).

Uruchamianie: ``py -m canstudio gui`` (patrz też `canstudio.tools.gui`).
"""

from __future__ import annotations

import asyncio
import threading
import time
import webbrowser
from collections import Counter, deque
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import can
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from .. import __version__
from .. import obd_log
from ..bridging import (BridgeRules, BridgeState, make_endpoint_args,
                        parse_endpoint, run_bridge, transform)
from ..buttonfinder import find_button
from ..bus import open_bus, serial_ports
from ..checksums import ALGORITHMS, analyze_frames
from ..annotations import AnnotationStore
from ..config import (LOGS_DIR, PROFILES_DIR, ROOT, list_profiles,
                      load_profile, resolve_path)
from ..dbc import load_dbc, signal_map
from ..dbcgen import build_dbc
from ..detect import classify_frames
from ..diffing import diff_logs
from ..frames import parse_id
from ..logio import read_log, trim_messages, write_candump
from ..markers import correlate as markers_correlate
from ..markers import read_candump_with_markers
from ..obd import PID_TABLE, ObdSession
from ..stats import IdStats, estimate_period, group_bytes_by_id
from ..vin import decode_vin

STATIC = Path(__file__).resolve().parent / "index.html"

# ---------------------------------------------------------------------------
# Menadżer magistrali
# ---------------------------------------------------------------------------


class _MitmGuiLogger:
    """Adapter zdarzeń bridge -> strumień GUI (z ograniczeniem częstości)."""

    def __init__(self, manager: "CanManager", direction: str):
        self.manager = manager
        self.direction = direction
        self.sent = 0
        self.mods = 0

    def line(self, msg, channel: str, modified: bool = False) -> None:
        try:
            payload = bytes(msg.data).hex().upper()
        except Exception:
            payload = "?"
        if modified:
            self.mods += 1
            show = self.mods <= 30 or self.mods % 20 == 0
            tag = f"{channel} ✱"
        else:
            self.sent += 1
            show = self.sent <= 10 or self.sent % 80 == 0
            tag = channel
        if show:
            self.manager._push_event({
                "t": "mitm",
                "m": f"{tag} 0x{msg.arbitration_id:03X}#{payload}"})


class CanManager:
    """Jedna magistrala + bufor na żywo + nagrywanie + TX (wątek czytający)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.bus = None
        self.reader = None
        self.stop_evt = threading.Event()
        self.connected = False
        self.config: dict = {}
        self.silent = True

        self.id_stats = IdStats(history=300)
        self.id_payloads: dict = {}
        self.total = 0
        self.recent: deque = deque(maxlen=300)

        self._live_lock = threading.Lock()
        self._live_frames: list = []
        self._live_events: list = []

        self.recording = False
        self.log_fh = None
        self.log_name = None

        self.dbc = None
        self.dbc_path = None
        self.dbc_names: dict = {}

        self._demo_bus = None
        self._demo_stop = threading.Event()

        self.tx_task: asyncio.Task | None = None
        self.tx_stop: asyncio.Event | None = None
        self.tx_state: dict = {"active": False, "sent": 0, "label": ""}

        self._fps_last_t = 0.0
        self._fps_last_total = 0
        self._fps = 0.0

        self.mitm: dict = {"active": False}
        self.pinned: dict = {}
        self.ring: deque = deque(maxlen=150000)
        self.trigger: dict | None = None
        self.uds_busy = threading.Event()
        self._uds_demo_stop: threading.Event | None = None
        self._uds_written: dict = {}
        self.annotations = AnnotationStore(ROOT / "profiles" / "bmw.json")
        self.replay: dict = {"active": False}
        self._replay_stop: threading.Event | None = None

    # ---------------- magistrala ----------------
    def open(self, interface: str, port: str, bitrate: int, silent: bool, demo: bool) -> dict:
        if self.connected:
            return {"ok": False, "error": "Już połączono — najpierw rozłącz."}
        args = SimpleNamespace(interface=interface, channel=port, bitrate=bitrate,
                               tty_baud=115200, silent=silent, silent_mode="m1", fd=False)
        try:
            self.bus = open_bus(args)
        except SystemExit as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            low = msg.lower()
            if "access is denied" in low or "permissionerror" in low:
                msg = (f"Port {port} jest zajęty (trzyma go inny program?). "
                       "Zamknij Cangaroo/CANHacker/inne narzędzie i spróbuj ponownie.")
            elif "could not open port" in low or "filenotfound" in low:
                msg = (f"Nie widzę portu {port} — sprawdź kabel USB "
                       "i odśwież listę portów (⟳).")
            return {"ok": False, "error": msg}
        self.connected = True
        self.silent = silent
        self.config = {"interface": interface, "channel": port, "bitrate": bitrate,
                       "silent": silent, "demo": demo}
        self.stop_evt.clear()
        self.reader = threading.Thread(target=self._read_loop, daemon=True)
        self.reader.start()
        if demo:
            self._start_demo()
        self._push_event({"t": "notice", "m": f"Połączono: {interface}:{port} @ {bitrate} bit/s"})
        return {"ok": True, **self.config}

    def close(self) -> dict:
        if not self.connected:
            return {"ok": True}
        self._stop_tx()
        if self._replay_stop is not None:
            self._replay_stop.set()
        self._stop_demo()
        self.mitm_stop()
        self.stop_evt.set()
        if self.reader:
            self.reader.join(timeout=1.0)
        try:
            self.bus.shutdown()
        except Exception:
            pass
        self.bus = None
        self.connected = False
        if self.recording:
            self.stop_recording()
        self._push_event({"t": "notice", "m": "Rozłączono"})
        return {"ok": True}

    def _read_loop(self) -> None:
        while not self.stop_evt.is_set():
            if self.uds_busy.is_set():
                time.sleep(0.02)  # pauza na czas operacji UDS (jedna magistrala)
                continue
            try:
                msg = self.bus.recv(timeout=0.2)
            except Exception:
                break
            if msg is None:
                continue
            self._handle(msg)
        # koniec pętli czytania: rozłączenie lub awaria
        if not self.stop_evt.is_set():
            self.connected = False
            self._push_event({"t": "notice", "m": "Magistrala rozłączona (błąd czytania)"})
            try:
                self.bus.shutdown()
            except Exception:
                pass

    def _handle(self, msg: can.Message) -> None:
        ts = getattr(msg, "timestamp", None) or time.time()
        aid = msg.arbitration_id
        data = bytes(msg.data)
        ext = bool(msg.is_extended_id)
        key = aid + (0x20000000 if ext else 0)
        self.ring.append((ts, aid, 1 if ext else 0, data))
        with self._live_lock:
            dq = self.id_payloads.get(key)
            if dq is None:
                dq = self.id_payloads[key] = deque(maxlen=300)
            dq.append(data)
        self.id_stats.add(key, ts, data)
        self.total += 1
        item = {"t": round(ts, 6), "id": aid, "x": 1 if ext else 0, "k": key,
                "n": self.annotations.name_for(key) or self.dbc_names.get(aid, ""),
                "d": data.hex().upper()}
        if self.pinned and self.dbc is not None and key in self.pinned:
            try:
                decoded = self.dbc.decode_message(aid, data)
                sig = {}
                for name in self.pinned.get(key, ()):
                    if name in decoded:
                        value = decoded[name]
                        sig[name] = value if isinstance(value, (int, float, str)) else str(value)
                if sig:
                    item["sig"] = sig
            except Exception:
                pass
        # trigger wokół zmiany wybranego bajtu (okno konfigurowalne)
        trg = self.trigger
        if trg is not None and key == trg["key"] and trg["byte"] < len(data):
            val = data[trg["byte"]]
            if trg.get("last") is not None and val != trg["last"] and not trg.get("collecting"):
                trg["collecting"] = True
                trg["hit_ts"] = ts
                self._push_event({"t": "trigger", "m": (
                    f"TRIGGER: zmiana wykryta — nagrywam -{trg.get('pre', 5.0):g}"
                    f" +{trg.get('post', 5.0):g} s...")})
            trg["last"] = val
        if (trg is not None and trg.get("collecting")
                and ts >= trg["hit_ts"] + trg.get("post", 5.0)):
            self._trigger_finish()
        self.recent.append(item)
        with self._live_lock:
            self._live_frames.append(item)
        if self.recording and self.log_fh is not None:
            try:
                line = (f"({ts:.6f}) gui {aid:08X}#{data.hex().upper()}" if ext
                        else f"({ts:.6f}) gui {aid:03X}#{data.hex().upper()}")
                self.log_fh.write(line + "\n")
            except Exception:
                pass

    # ---------------- nagrywanie / znaczniki ----------------
    def start_recording(self) -> dict:
        if not self.connected:
            return {"ok": False, "error": "Brak połączenia."}
        if self.recording:
            return {"ok": True, "file": self.log_name}
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        name = "gui_" + time.strftime("%Y%m%d_%H%M%S") + ".log"
        path = LOGS_DIR / name
        self.log_fh = open(path, "w", encoding="utf-8", buffering=1)
        self.recording = True
        self.log_name = str(path)
        self._push_event({"t": "notice", "m": f"REC → {name}"})
        return {"ok": True, "file": self.log_name, "name": name}

    def stop_recording(self) -> dict:
        was = self.recording
        if self.log_fh is not None:
            try:
                self.log_fh.close()
            except Exception:
                pass
        self.log_fh = None
        self.recording = False
        if was:
            self._push_event({"t": "notice", "m": "REC zatrzymany"})
        return {"ok": True}

    def add_mark(self, label: str) -> dict:
        label = (label or "mark").strip()
        ts = time.time()
        if self.recording and self.log_fh is not None:
            self.log_fh.write(f"# MARK {ts:.6f} {label}\n")
        self._push_event({"t": "notice", "m": f"MARK: {label}"})
        return {"ok": True, "saved": bool(self.recording)}

    # ---------------- wysyłka (TX) ----------------
    async def start_tx(self, params: dict) -> dict:
        if not self.connected:
            return {"ok": False, "error": "Brak połączenia."}
        if self.config.get("interface") == "slcan" and self.silent:
            return {"ok": False, "error": "Tryb bierny (silent) — nadawanie wymaga trybu normalnego (odznacz silent i połącz ponownie)."}
        if self.tx_state.get("active"):
            return {"ok": False, "error": "Wysyłka już trwa — najpierw ZATRZYMAJ."}
        try:
            job = self._build_tx_job(params)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        self.tx_stop = asyncio.Event()
        self.tx_state = {"active": True, "sent": 0, "label": job["label"]}
        self.tx_task = asyncio.create_task(self._tx_loop(job))
        self._push_event({"t": "tx", "m": f"TX start: {job['label']}"})
        return {"ok": True, "label": job["label"]}

    def stop_tx(self) -> dict:
        if self.tx_stop:
            self.tx_stop.set()
        return {"ok": True}

    def _stop_tx(self) -> None:
        if self.tx_stop:
            self.tx_stop.set()

    def _build_tx_job(self, p: dict) -> dict:
        from ..bridging import BridgeRules, ChecksumRule, CounterRule
        aid = parse_id(str(p.get("id", "")))
        data_hex = str(p.get("data", "")).replace(" ", "").replace(":", "")
        data = bytes.fromhex(data_hex) if data_hex else b""
        if len(data) > 8:
            raise ValueError("Klasyczny CAN: maks. 8 bajtów.")
        sweep = None
        if p.get("sweep"):
            parts = str(p["sweep"]).split(":")
            if len(parts) < 2:
                raise ValueError("Sweep: format BAJT:START-END[:STEP]")
            byte = int(parts[0], 0)
            a, _, b = parts[1].partition("-")
            start, end = parse_id(a), parse_id(b)
            step = int(parts[2], 0) if len(parts) > 2 else 1
            if len(data) <= byte:
                raise ValueError("Sweep: za krótkie dane.")
            sweep = (byte, min(start, end), max(start, end), max(1, step))
        rules = None
        if p.get("counter") not in (None, "") or p.get("checksum"):
            rules = BridgeRules()
            if p.get("counter") not in (None, ""):
                rules.counter_rules.append(CounterRule(aid, int(p["counter"])))
            if p.get("checksum"):
                byte_s, _, algo = str(p["checksum"]).partition(":")
                rules.checksum_rules.append(ChecksumRule(aid, int(byte_s, 0), algo))
        count = int(p.get("count", 1) or 0)
        interval = float(p.get("interval", 0.1) or 0.1)
        return {"aid": aid, "data": data, "ext": bool(p.get("extended")),
                "count": count, "interval": interval, "sweep": sweep, "rules": rules,
                "label": f"0x{aid:X} co {interval * 1000:.0f} ms"
                         + (" (∞)" if not count else f" x{count}")}

    async def _tx_loop(self, job: dict) -> None:
        from ..bridging import BridgeState, transform
        state = BridgeState() if job["rules"] else None
        sent = 0
        sw = job["sweep"][1] if job["sweep"] else None
        try:
            while not (self.tx_stop and self.tx_stop.is_set()):
                payload = bytearray(job["data"])
                if job["sweep"]:
                    payload[job["sweep"][0]] = sw
                    sw += job["sweep"][3]
                    if sw > job["sweep"][2]:
                        sw = job["sweep"][1]
                if state is not None:
                    payload = bytearray(transform(bytes(payload), job["aid"],
                                                  job["rules"], state, "gui")[0])
                msg = can.Message(arbitration_id=job["aid"], is_extended_id=job["ext"],
                                  data=bytes(payload))
                ok = await asyncio.to_thread(self._send_msg, msg)
                sent += 1
                self.tx_state["sent"] = sent
                if sent <= 20 or sent % 50 == 0:
                    self._push_event({"t": "tx",
                                      "m": f"TX {sent}: 0x{job['aid']:X} "
                                           f"{bytes(payload).hex(' ').upper()}"
                                           + ("" if ok else "  (BŁĄD)")})
                if job["count"] and sent >= job["count"]:
                    break
                await asyncio.sleep(job["interval"])
        finally:
            self.tx_state["active"] = False
            self._push_event({"t": "tx", "m": f"TX zakończono (wysłano {sent})"})

    def _send_msg(self, msg: can.Message) -> bool:
        try:
            with self.lock:
                self.bus.send(msg)
            return True
        except Exception:
            return False

    # ---------------- demo (wirtualna magistrala) ----------------
    def _start_demo(self) -> None:
        channel = str(self.config.get("channel") or "gui-demo")
        self._demo_bus = can.Bus(interface="virtual", channel=channel)
        self._demo_stop.clear()
        threading.Thread(target=self._demo_loop, daemon=True).start()
        self._start_uds_demo()

    def _stop_demo(self) -> None:
        self._demo_stop.set()
        if self._uds_demo_stop is not None:
            self._uds_demo_stop.set()
            self._uds_demo_stop = None
        if self._demo_bus is not None:
            try:
                self._demo_bus.shutdown()
            except Exception:
                pass
            self._demo_bus = None

    def _demo_loop(self) -> None:
        import math
        defs = [(0x130, 8, 20, False), (0x1A0, 8, 20, False), (0x316, 8, 20, False),
                (0x1D2, 8, 20, False), (0x0AA, 8, 10, False), (0x0C0, 6, 5, False),
                (0x18DAF110, 8, 5, True)]
        counters: dict = {}
        i = 0
        while not self._demo_stop.is_set() and not self.stop_evt.is_set():
            i += 1
            for aid, dlc, hz, ext in defs:
                if i % max(1, round(20 / hz)) != 0:
                    continue
                c = counters.get(aid, 0)
                counters[aid] = (c + 1) & 0xFF
                spd = 84 + 36 * math.sin(i / 53)
                eng = 900 + 2100 * (0.5 + 0.5 * math.sin(i / 37))
                if aid == 0x130:
                    body = [0x03, c, 0x10, int(spd) & 0xFF, 0x80,
                            int(eng / 12) & 0xFF, int(eng * 2.44) & 0xFF, 0]
                    body[7] = 0
                    for x in body[:7]:
                        body[7] ^= x
                elif aid == 0x0C0:
                    body = [c, 0x81, 0x00, 0x02, 0x03, 0x04]
                elif aid == 0x18DAF110:
                    body = [0x62, c, (i * 11) & 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00]
                else:
                    body = [0x11, c, (i * 7) & 0xFF, (i * 3) & 0xFF,
                            0x40, 0x00, 0x00, 0x00][:dlc]
                try:
                    self._demo_bus.send(can.Message(arbitration_id=aid, data=bytes(body),
                                                    is_extended_id=ext))
                except Exception:
                    pass
            time.sleep(0.02)

    # ---------------- UDS (diagnostyka; panel GUI) ----------------
    def _uds_demo_handle(self, req: bytes):
        """Mini-ECU do trybu demo (odpowiada po UDS na 0x6F1 jak sterownik)."""
        sid = req[0]
        if sid == 0x3E:
            if len(req) > 1 and req[1] & 0x80:
                return None
            return bytes([0x7E, req[1] if len(req) > 1 else 0])
        if sid == 0x10:
            return bytes([0x50, req[1] if len(req) > 1 else 0x01, 0x00, 0x32, 0x01, 0xF4])
        if sid == 0x22:
            did = int.from_bytes(req[1:3], "big")
            if did == 0xF190:
                return b"\x62\xF1\x90" + b"WBA5E510X0G123456"
            if did == 0xF18C:
                return b"\x62\xF1\x8C" + b"SN-DEMO-0001"
            if did == 0xF187:
                return b"\x62\xF1\x87BMW 6885582"
            if did == 0xF18B:
                return b"\x62\xF1\x8B" + b"2026-10-07"
            if did in self._uds_written:
                return bytes([0x62]) + req[1:3] + self._uds_written[did]
            return bytes([0x7F, 0x22, 0x31])
        if sid == 0x2E:
            did = int.from_bytes(req[1:3], "big")
            self._uds_written[did] = bytes(req[3:])
            return bytes([0x6E]) + req[1:3]
        if sid == 0x19:
            return (b"\x59\x02\xFF" + bytes([0x12, 0x34, 0x56, 0x24])
                    + bytes([0xAB, 0xC0, 0x01, 0x2F]))
        if sid == 0x14:
            return b"\x54"
        if sid == 0x11:
            return bytes([0x51, req[1] if len(req) > 1 else 0x01])
        return bytes([0x7F, sid, 0x11])

    def _start_uds_demo(self) -> None:
        """Demo: wirtualny sterownik UDS na tej samej magistrali (0x6F1 -> 0x6F9)."""
        try:
            from .. import diag

            diag.require_deps()
        except SystemExit:
            return
        self._uds_demo_stop = threading.Event()
        threading.Thread(target=self._uds_demo_loop,
                         args=(self._uds_demo_stop,), daemon=True).start()

    def _uds_demo_loop(self, stop: threading.Event) -> None:
        from .. import diag

        channel = str(self.config.get("channel") or "gui-demo")
        try:
            bus = can.Bus(interface="virtual", channel=channel)
        except Exception:
            return
        tp = diag.open_isotp(bus, 0x6F9, 0x6F1)
        tp.start()
        try:
            while not stop.is_set() and not self.stop_evt.is_set():
                req = tp.recv(block=True, timeout=0.1)
                if not req:
                    continue
                resp = self._uds_demo_handle(bytes(req))
                if resp:
                    tp.send(resp)
        finally:
            diag.close_session(bus=bus, tp=tp)

    def _uds_pause(self) -> bool:
        """Wstrzymuje pętlę czytającą na czas operacji UDS (współdzielona magistrala)."""
        if not self.connected or self.bus is None or self.uds_busy.is_set():
            return False
        self.uds_busy.set()
        time.sleep(0.25)  # bieżące recv w readerze zdąży wrócić
        return True

    @staticmethod
    def _uds_value(r, did: int) -> bytes:
        from .. import diag

        val = diag.did_value(r, did)
        if isinstance(val, (bytes, bytearray)):
            return bytes(val)
        return str(val).encode("ascii", "replace")

    def uds_scan(self, p: dict) -> dict:
        from .. import diag

        try:
            diag.require_deps()
        except SystemExit as exc:
            return {"ok": False, "error": str(exc)}
        if self.uds_busy.is_set():
            return {"ok": False, "error": "Operacja UDS już trwa."}
        if not self._uds_pause():
            return {"ok": False, "error": "Najpierw połącz z magistralą."}
        try:
            ids = diag.parse_ids_spec(str(p.get("ids") or "600-6FF"))[:512]
            offset = max(0, min(0x200, int(p.get("offset") or 8)))
            timeout = max(0.005, min(1.0, float(p.get("timeout_ms") or 50) / 1000.0))
            probe = diag.parse_hex_bytes(str(p.get("probe") or "3E00"))
            log = diag.open_log("uds_gui")
            log.note(f"scan (gui): {len(ids)} adresów, offset {offset}, timeout {timeout:.3f}s")
            results: list = []

            def on_result(res):
                if res["resp"] is None:
                    return
                hexs = " ".join(f"{b:02X}" for b in res["resp"])
                results.append({"txid": res["txid"], "rxid": res["rxid"],
                                "payload": hexs})
                self._push_event({"t": "uds", "m": f"ECU 0x{res['txid']:03X} -> "
                                                   f"0x{res['rxid']:03X}: {hexs}"})

            def on_progress(i, total):
                if i % 32 == 0 or i == total:
                    self._push_event({"t": "uds", "m": f"skan {i}/{total}..."})

            diag.scan_ecus(self.bus, ids, offset=offset, probe=probe, timeout=timeout,
                           on_progress=on_progress, on_result=on_result, log=log)
            log.close()
            return {"ok": True, "checked": len(ids), "count": len(results),
                    "results": results}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            self.uds_busy.clear()

    def uds_read(self, p: dict) -> dict:
        return self._uds_client_op("read", p)

    def uds_write(self, p: dict) -> dict:
        if not p.get("confirm"):
            return {"ok": False, "error": "Zapis wymaga potwierdzenia (confirm=true)."}
        return self._uds_client_op("write", p)

    def uds_dtc(self, p: dict) -> dict:
        if p.get("clear") and not p.get("confirm"):
            return {"ok": False, "error": "Kasowanie DTC wymaga potwierdzenia (confirm=true)."}
        return self._uds_client_op("dtc", p)

    def _uds_client_op(self, kind: str, p: dict) -> dict:
        from .. import diag

        try:
            diag.require_deps()
        except SystemExit as exc:
            return {"ok": False, "error": str(exc)}
        if self.uds_busy.is_set():
            return {"ok": False, "error": "Operacja UDS już trwa."}
        if not self._uds_pause():
            return {"ok": False, "error": "Najpierw połącz z magistralą."}
        tp = None
        conn = None
        log = None
        try:
            tx = diag.parse_hex(str(p.get("txid") or ""))
            rx = diag.parse_hex(str(p["rxid"])) if p.get("rxid") else tx + 8
            session = diag.parse_hex(str(p["session"])) if p.get("session") else None
            log = diag.open_log("uds_gui")
            log.note(f"{kind} (gui): txid=0x{tx:X} rxid=0x{rx:X} session={session}")
            tp = diag.open_isotp(self.bus, tx, rx, extended=bool(p.get("ext")))
            client, conn = diag.make_client(tp, log)
            out: dict = {"ok": True, "txid": tx, "rxid": rx}
            if session:
                r = client.change_session(session)
                out["session_ok"] = bool(r.positive)
            if kind == "read":
                dids = [diag.parse_hex(str(x)) for x in (p.get("dids") or ["F190"])][:32]
                items = []
                for did in dids:
                    r = client.read_data_by_identifier(did)
                    item = {"did": did, "name": diag.did_name(did),
                            "positive": bool(r.positive)}
                    if r.positive:
                        val = self._uds_value(r, did)
                        item["hex"] = " ".join(f"{b:02X}" for b in val)
                        if val and all(32 <= b < 127 for b in val):
                            item["text"] = val.decode("ascii", "replace")
                    else:
                        item["code"] = diag.code_name(r.code)
                    items.append(item)
                out["dids"] = items
            elif kind == "write":
                did = diag.parse_hex(str(p.get("did") or ""))
                data = diag.parse_hex_bytes(str(p.get("data") or ""))
                r = client.write_data_by_identifier(did, data)
                out["did"] = did
                out["written"] = " ".join(f"{b:02X}" for b in data)
                if not r.positive:
                    out["ok"] = False
                    out["error"] = f"ODMOWA: {diag.code_name(r.code)}"
            elif kind == "dtc":
                mask = diag.parse_hex(str(p.get("mask") or "FF"))
                r = client.get_dtc_by_status_mask(mask)
                if r.positive:
                    sd = r.service_data
                    dtcs = list(getattr(sd, "dtcs", None) or [])
                    out["count"] = getattr(sd, "dtc_count", None)
                    out["dtcs"] = []
                    for d in dtcs:
                        status = None
                        try:
                            status = int(d.status.get_byte_as_int())
                        except Exception:  # noqa: BLE001
                            pass
                        out["dtcs"].append({"id": d.id, "status": status,
                                            "text": diag.fmt_dtc(d)})
                else:
                    out["ok"] = False
                    out["error"] = f"ODMOWA: {diag.code_name(r.code)}"
                if p.get("clear"):
                    r2 = client.clear_dtc()
                    out["cleared"] = bool(r2.positive)
                    if not r2.positive:
                        out["clear_error"] = diag.code_name(r2.code)
            return out
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            if log is not None:
                log.close()
            if tp is not None or conn is not None:
                diag.close_session(bus=None, tp=tp, conn=conn)
            self.uds_busy.clear()

    # ---------------- MITM (man in the middle, bench) ----------------
    def mitm_start(self, p: dict) -> dict:
        if self.mitm.get("active"):
            return {"ok": False, "error": "MITM już aktywny."}
        demo = bool(p.get("demo"))
        if not demo and self.connected:
            return {"ok": False, "error": "Najpierw rozłącz główną magistralę (współdzielone porty)."}
        spec_in = str(p.get("in", "")).strip()
        spec_out = str(p.get("out", "")).strip()
        if not demo and (not spec_in or not spec_out):
            return {"ok": False, "error": "Podaj kanały IN i OUT (np. slcan:COM7 / slcan:COM8)."}
        try:
            rules = BridgeRules.from_mapping(p.get("rules") or {})
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"Błędne reguły: {exc}"}
        rules.tap = bool(p.get("tap"))
        bitrate = int(p.get("bitrate", 500000))

        stop = threading.Event()
        stats = {"fwd": 0, "mod": 0, "dropped": 0, "errors": 0}
        buses: list = []
        threads: list = []
        gen_bus = None
        gen_stop = None
        try:
            if demo:
                chin, chout = "mitm-demo-in", "mitm-demo-out"
                spec_in, spec_out = f"virtual:{chin}", f"virtual:{chout}"
                gen_bus = can.Bus(interface="virtual", channel=chin)
                bus_in = can.Bus(interface="virtual", channel=chin)
                bus_out = can.Bus(interface="virtual", channel=chout)
                gen_stop = threading.Event()
                threading.Thread(target=self._mitm_demo_gen,
                                 args=(gen_bus, gen_stop), daemon=True).start()
            else:
                iface_in, ch_in = parse_endpoint(spec_in)
                iface_out, ch_out = parse_endpoint(spec_out)
                bus_in = open_bus(make_endpoint_args(iface_in, ch_in, bitrate))
                bus_out = open_bus(make_endpoint_args(iface_out, ch_out, bitrate))
            buses += [bus_in, bus_out]
            threads.append(threading.Thread(
                target=run_bridge,
                args=(bus_in, bus_out, rules, "A>B", _MitmGuiLogger(self, "A>B"),
                      stop, 0.05, stats), daemon=True))
            threads.append(threading.Thread(
                target=run_bridge,
                args=(bus_out, bus_in, rules, "B>A", _MitmGuiLogger(self, "B>A"),
                      stop, 0.05, stats), daemon=True))
            for t in threads:
                t.start()
        except SystemExit as exc:
            for b in buses:
                try:
                    b.shutdown()
                except Exception:
                    pass
            if gen_bus is not None:
                try:
                    gen_bus.shutdown()
                except Exception:
                    pass
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            for b in buses:
                try:
                    b.shutdown()
                except Exception:
                    pass
            if gen_bus is not None:
                try:
                    gen_bus.shutdown()
                except Exception:
                    pass
            return {"ok": False, "error": str(exc)}

        self.mitm = {"active": True, "demo": demo, "tap": rules.tap, "stop": stop,
                     "stats": stats, "threads": threads, "buses": buses,
                     "gen_bus": gen_bus, "gen_stop": gen_stop,
                     "in": spec_in, "out": spec_out}
        self._push_event({"t": "notice",
                          "m": f"MITM start ({'demo' if demo else spec_in + ' ↔ ' + spec_out})"})
        return {"ok": True, "demo": demo, "in": spec_in, "out": spec_out}

    def mitm_stop(self) -> dict:
        m = self.mitm or {}
        if not m.get("active"):
            return {"ok": True}
        m["stop"].set()
        if m.get("gen_stop") is not None:
            m["gen_stop"].set()
        for t in m.get("threads", []):
            t.join(timeout=1.0)
        for b in list(m.get("buses", [])):
            try:
                b.shutdown()
            except Exception:
                pass
        if m.get("gen_bus") is not None:
            try:
                m["gen_bus"].shutdown()
            except Exception:
                pass
        m["active"] = False
        self._push_event({"t": "notice", "m": "MITM zatrzymany"})
        return {"ok": True}

    def mitm_status(self) -> dict:
        m = self.mitm or {}
        return {"active": bool(m.get("active")), "demo": m.get("demo"),
                "tap": m.get("tap"), "in": m.get("in"), "out": m.get("out"),
                "stats": dict(m.get("stats") or {})}

    def _mitm_demo_gen(self, gen_bus, stop_evt: threading.Event) -> None:
        counters: dict = {}
        i = 0
        while not stop_evt.is_set() and not self.stop_evt.is_set():
            i += 1
            for aid, every in ((0x130, 1), (0x1A0, 1), (0x0AA, 2)):
                if i % every:
                    continue
                c = counters.get(aid, 0)
                counters[aid] = (c + 1) & 0xFF
                if aid == 0x130:
                    body = [0x03, c, 0x10, (i * 3) & 0xFF, 0x80, 0x00, 0x00, 0]
                    body[7] = 0
                    for x in body[:7]:
                        body[7] ^= x
                elif aid == 0x1A0:
                    body = [0x11, c, (i * 7) & 0xFF, 0x40, 0x00, 0x00, 0x00, 0x00]
                else:
                    body = [c, 0x22, (i * 5) & 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00]
                try:
                    gen_bus.send(can.Message(arbitration_id=aid, data=bytes(body),
                                             is_extended_id=False))
                except Exception:
                    pass
            time.sleep(0.02)

    # ---------------- trigger ±5 s ----------------
    def _trigger_finish(self) -> None:
        trg = self.trigger
        if not trg or not trg.get("collecting"):
            return
        hit = trg["hit_ts"]
        lo, hi = hit - trg.get("pre", 5.0), hit + trg.get("post", 5.0)
        frames = [f for f in self.ring if lo <= f[0] <= hi]
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        name = "trigger_" + time.strftime("%Y%m%d_%H%M%S") + ".log"
        path = LOGS_DIR / name
        try:
            with open(path, "w", encoding="utf-8") as fh:
                for ts, aid, ext, data in frames:
                    sid = f"{aid:08X}" if ext else f"{aid:03X}"
                    fh.write(f"({ts:.6f}) trig {sid}#{data.hex().upper()}\n")
        except Exception as exc:  # noqa: BLE001
            self._push_event({"t": "trigger", "m": f"TRIGGER: błąd zapisu: {exc}"})
            self.trigger = None
            return
        self._push_event({"t": "trigger",
                          "m": f"TRIGGER zapisany: {name} ({len(frames)} ramek)"})
        if trg.get("keep"):
            self.trigger = {"key": trg["key"], "byte": trg["byte"], "last": trg.get("last"),
                            "collecting": False, "hit_ts": None,
                            "pre": trg.get("pre", 5.0), "post": trg.get("post", 5.0),
                            "keep": True}
            self._push_event({"t": "trigger",
                              "m": "TRIGGER: uzbrojony ponownie (tryb ciągły)"})
        else:
            self.trigger = None

    # ---------------- DBC / insight ----------------
    def load_dbc_file(self, path: str) -> dict:
        try:
            db = load_dbc(resolve_path(path))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        self.dbc = db
        self.dbc_path = str(path)
        self.dbc_names = {m.frame_id: m.name for m in db.messages}
        return {"ok": True, "name": Path(path).name, "messages": len(self.dbc_names)}

    def id_insight(self, key: int) -> dict:
        if key >= 0x20000000:
            aid, ext = key - 0x20000000, True
        else:
            aid, ext = key, False
        with self._live_lock:
            payloads = list(self.id_payloads.get(key, []))
        info = {
            "key": key,
            "id": aid,
            "ext": ext,
            "count": self.id_stats.counts.get(key, 0),
            "period": self.id_stats.period(key),
            "dlc": len(payloads[-1]) if payloads else None,
            "last": payloads[-1].hex(" ").upper() if payloads else None,
        }
        if payloads and len(payloads) >= 12:
            try:
                classes = classify_frames(payloads[-300:])
                info["classes"] = [{"b": c.byte, "k": c.kind, "d": c.detail}
                                   for c in classes]
            except Exception:
                pass
        if self.dbc is not None and payloads:
            try:
                decoded = self.dbc.decode_message(aid, payloads[-1])
                info["decoded"] = {k: (v if isinstance(v, (int, float, str)) else str(v))
                                   for k, v in decoded.items()}
            except Exception:
                pass
        if self.dbc is not None and payloads:
            try:
                smap = signal_map(self.dbc, aid)
            except Exception:
                smap = None
            if smap:
                cls_by_byte = {c["b"]: c["k"] for c in info.get("classes", [])}
                byte_sigs: dict = {}
                sigs_out = []
                for s in smap["signals"]:
                    cov = [cls_by_byte[b] for b in s["bytes"] if b in cls_by_byte]
                    mixed = len(set(cov)) > 1
                    warn = (sorted({k for k in cov if k.startswith(("licznik", "suma"))})
                            if mixed else [])
                    sigs_out.append({
                        "name": s["name"], "first": s["first"], "last": s["last"],
                        "unit": s["unit"], "cls": cov, "warn": warn,
                        "conf": [b for b in s["bytes"]
                                 if cls_by_byte.get(b, "").startswith(("licznik", "suma"))],
                    })
                    for b in s["bytes"]:
                        byte_sigs.setdefault(str(b), []).append(s["name"])
                dlc = info.get("dlc") or 0
                info["link"] = {
                    "signals": sigs_out,
                    "byte_sigs": byte_sigs,
                    "uncovered": [b for b in range(dlc) if str(b) not in byte_sigs],
                }
        info["ann"] = self.annotations.get(key)
        return info

    # ---------------- anotacje / profile ----------------
    def load_profile_annotations(self, name: str) -> dict:
        p = PROFILES_DIR / f"{name}.json"
        if not p.exists():
            return {"ok": False, "error": f"Nie ma profilu {name}.json"}
        data = self.annotations.load(p)
        self._push_event({"t": "notice", "m": f"Profil: {p.name} (anotacji: {len(data)})"})
        return {"ok": True, "name": p.name, "annotations": data}

    def set_annotation(self, p: dict) -> dict:
        try:
            key = int(p.get("key", 0) or 0)
        except (TypeError, ValueError):
            key = 0
        if key <= 0:
            return {"ok": False, "error": "Brak ID"}
        name = str(p.get("name") or "").strip()[:60]
        note = str(p.get("note") or "").strip()[:400]
        self.annotations.set(key, name, note)
        return {"ok": True, "key": key, "name": name, "note": note}

    # ---------------- menedżer logów ----------------
    def log_stats(self, path: str) -> dict:
        try:
            p = _resolve_log(path)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        messages = read_log(p)
        if not messages:
            return {"ok": False, "error": "Pusty log."}
        stats = IdStats()
        for m in messages:
            ext = bool(getattr(m, "is_extended_id", False))
            stats.add(m.arbitration_id + (0x20000000 if ext else 0), m.timestamp)
        duration = (messages[-1].timestamp or 0) - (messages[0].timestamp or 0)
        top = []
        for key, cnt in stats.top(12):
            ext = key >= 0x20000000
            top.append({"id": key - 0x20000000 if ext else key, "ext": ext,
                        "count": cnt, "period": stats.period(key)})
        return {"ok": True, "file": p.name, "frames": len(messages),
                "ids": len(stats.counts), "duration": round(duration, 3),
                "top": top}

    def log_trim(self, p: dict) -> dict:
        try:
            src = _resolve_log(str(p.get("file", "")))
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        messages = read_log(src)

        def _f(name):
            v = p.get(name)
            return float(v) if v not in (None, "") else None

        def _i(name):
            v = p.get(name)
            return int(v) if v not in (None, "") else 0

        trimmed = trim_messages(messages, from_s=_f("from_s"), to_s=_f("to_s"),
                                offset=_i("offset"), count=_i("count"))
        if not trimmed:
            return {"ok": False, "error": "Zakres pusty — nic nie zostało."}
        out = LOGS_DIR / ("trim_" + src.stem + "_" + time.strftime("%Y%m%d_%H%M%S") + ".log")
        write_candump(out, trimmed)
        self._push_event({"t": "notice",
                          "m": f"Przycięto {src.name}: {len(trimmed)} ramek → {out.name}"})
        return {"ok": True, "file": out.name, "name": src.name, "frames": len(trimmed)}

    def log_replay_start(self, p: dict) -> dict:
        if not self.connected or self.bus is None:
            return {"ok": False, "error": "Najpierw połącz z magistralą."}
        if self.replay.get("active"):
            return {"ok": False, "error": "Odtwarzanie już trwa."}
        try:
            src = _resolve_log(str(p.get("file", "")))
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        messages = read_log(src)
        if not messages:
            return {"ok": False, "error": "Pusty log."}
        try:
            rules = BridgeRules.from_mapping(p.get("rules") or {})
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"Błędne reguły: {exc}"}
        rate = float(p.get("rate") or 1.0)
        loop = bool(p.get("loop"))
        limit = int(p.get("limit") or 0)
        stop = threading.Event()
        self._replay_stop = stop
        self.replay = {"active": True, "file": src.name, "sent": 0,
                       "total": len(messages)}
        threading.Thread(target=self._replay_loop,
                         args=(messages, rules, rate, loop, limit, stop),
                         daemon=True).start()
        return {"ok": True, "file": src.name, "total": len(messages)}

    def log_replay_stop(self) -> dict:
        if self._replay_stop is not None:
            self._replay_stop.set()
        return {"ok": True}

    def _replay_loop(self, messages, rules, rate, loop, limit, stop) -> None:
        rate = rate if rate > 0 else 1.0
        sent = 0
        modified = 0
        state = BridgeState()
        self._push_event({"t": "replay", "m": f"start: {len(messages)} ramek (x{rate:g})"})
        try:
            while True:
                prev_ts = messages[0].timestamp or 0.0
                schedule = 0.0
                t0 = time.monotonic()
                for m in messages:
                    if stop.is_set():
                        break
                    ts = m.timestamp or prev_ts
                    schedule += max(0.0, min(ts - prev_ts, 5.0)) / rate
                    prev_ts = ts
                    now = time.monotonic() - t0
                    if schedule > now:
                        if stop.wait(timeout=min(schedule - now, 0.5)):
                            break
                    if m.arbitration_id in rules.drop_ids:
                        continue
                    data, was_mod = transform(bytes(m.data), m.arbitration_id,
                                              rules, state, "replay")
                    if was_mod:
                        modified += 1
                    self._send_msg(can.Message(arbitration_id=m.arbitration_id,
                                               is_extended_id=bool(m.is_extended_id),
                                               data=data))
                    sent += 1
                    self.replay["sent"] = sent
                    if limit and sent >= limit:
                        stop.set()
                        break
                    if sent % 100 == 0:
                        self._push_event({"t": "replay", "m": f"... {sent}/{len(messages)}"})
                if stop.is_set() or not loop:
                    break
        finally:
            self.replay = {"active": False, "sent": sent, "total": len(messages)}
            self._push_event({"t": "replay",
                              "m": f"koniec: wysłano {sent}"
                                   + (f", zmodyfikowano {modified}" if modified else "")})

    # ---------------- status / bufor ----------------
    def status(self) -> dict:
        now = time.time()
        if self.trigger and self.trigger.get("collecting") and now > self.trigger["hit_ts"] + self.trigger.get("post", 5.0) + 1.0:
            self._trigger_finish()
        if self._fps_last_t:
            self._fps = (self.total - self._fps_last_total) / max(1e-6, now - self._fps_last_t)
        self._fps_last_t = now
        self._fps_last_total = self.total
        return {
            "connected": self.connected,
            "config": self.config,
            "recording": self.recording,
            "log": self.log_name,
            "dbc": Path(self.dbc_path).name if self.dbc_path else None,
            "tx": dict(self.tx_state),
            "replay": dict(self.replay),
            "total": self.total,
            "ids": len(self.id_stats.counts),
            "fps": round(self._fps, 1),
            "version": __version__,
            "profile": self.annotations.path.name if self.annotations.path else None,
            "ann": len(self.annotations.data),
            "trigger": ({"armed": True, "key": self.trigger["key"],
                         "byte": self.trigger["byte"],
                         "collecting": bool(self.trigger.get("collecting"))}
                        if self.trigger else None),
        }

    def stats_snapshot(self, top: int = 300) -> dict:
        return {str(aid): {"c": cnt, "p": self.id_stats.period(aid)}
                for aid, cnt in self.id_stats.top(top)}

    def snapshot_frames(self) -> list:
        return list(self.recent)

    def drain(self):
        with self._live_lock:
            frames, self._live_frames = self._live_frames, []
            events, self._live_events = self._live_events, []
        return frames, events

    def _push_event(self, event: dict) -> None:
        with self._live_lock:
            self._live_events.append(event)


# ---------------------------------------------------------------------------
# Aplikacja
# ---------------------------------------------------------------------------

manager: CanManager | None = None
CLIENTS: set = set()
SERVER_REF = None
IDLE_EXIT = 0
LAST_ACTIVITY = 0.0
obd_session: "ObdSession | None" = None


def _obd_push(ev: dict) -> None:
    """Zdarzenia OBD -> strumien GUI (przez menadzera magistrali)."""
    mgr = manager
    if mgr is not None:
        mgr._push_event(ev)


def _obd() -> ObdSession:
    """Sesja OBD (leniwe tworzenie; wspolna dla wszystkich endpointow)."""
    global obd_session
    if obd_session is None:
        obd_session = ObdSession(push=_obd_push)
    return obd_session


async def _broadcaster() -> None:
    last_stats = 0.0
    while True:
        await asyncio.sleep(0.05)
        if manager is None:
            continue
        frames, events = manager.drain()
        if frames or events:
            msg: dict = {"type": "update", "events": events}
            if frames:
                if len(frames) > 800:
                    frames = frames[-800:]
                msg["frames"] = frames
            dead = []
            for ws in CLIENTS:
                try:
                    await ws.send_json(msg)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                CLIENTS.discard(ws)
        now = time.time()
        if now - last_stats >= 0.5:
            last_stats = now
            snap = {"type": "stats", "stats": manager.stats_snapshot(),
                    "session": manager.status()}
            dead = []
            for ws in CLIENTS:
                try:
                    await ws.send_json(snap)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                CLIENTS.discard(ws)


async def _idle_watchdog() -> None:
    """Zamyka serwer, gdy przez IDLE_EXIT s nikt nie ma otwartego GUI."""
    while True:
        await asyncio.sleep(2)
        if IDLE_EXIT <= 0 or CLIENTS:
            continue
        if time.time() - LAST_ACTIVITY < IDLE_EXIT:
            continue
        print(f"# Brak aktywnego GUI od {IDLE_EXIT}s — zamykam serwer (zwalniam port COM).",
              flush=True)
        try:
            if manager is not None:
                await asyncio.to_thread(manager.close)
        except Exception:
            pass
        if SERVER_REF is not None:
            SERVER_REF.should_exit = True
        return


@asynccontextmanager
async def _lifespan(app: FastAPI):
    tasks = [asyncio.create_task(_broadcaster()),
             asyncio.create_task(_idle_watchdog())]
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="miriCAN Studio", lifespan=_lifespan)


@app.middleware("http")
async def _touch_activity(request, call_next):
    global LAST_ACTIVITY
    LAST_ACTIVITY = time.time()
    return await call_next(request)


@app.get("/")
async def index():
    return FileResponse(STATIC)


@app.get("/api/ports")
async def api_ports():
    out = []
    for p in serial_ports():
        out.append({"device": p.device, "desc": p.description,
                    "canable": bool(p.vid == 0x16D0 and p.pid == 0x117E)})
    return {"ports": out}


@app.post("/api/connect")
async def api_connect(payload: dict):
    return manager.open(str(payload.get("interface", "slcan")),
                        str(payload.get("port", "")),
                        int(payload.get("bitrate", 500000)),
                        bool(payload.get("silent", True)),
                        bool(payload.get("demo", False)))


@app.post("/api/disconnect")
async def api_disconnect():
    return manager.close()


@app.get("/api/status")
async def api_status():
    return manager.status()


@app.post("/api/record/start")
async def api_record_start():
    return manager.start_recording()


@app.post("/api/record/stop")
async def api_record_stop():
    return manager.stop_recording()


@app.post("/api/mark")
async def api_mark(payload: dict):
    return manager.add_mark(str(payload.get("label", "")))


@app.post("/api/send")
async def api_send(payload: dict):
    return await manager.start_tx(payload)


@app.post("/api/send/stop")
async def api_send_stop():
    return manager.stop_tx()


@app.get("/api/id/{key}")
async def api_id(key: int):
    return manager.id_insight(key)


@app.post("/api/pins")
async def api_pins(payload: dict):
    pins: dict = {}
    for p in payload.get("pins", []):
        try:
            aid = parse_id(str(p.get("id", "")))
        except Exception:
            continue
        key = aid + (0x20000000 if p.get("ext") else 0)
        name = str(p.get("signal", ""))
        if name:
            pins.setdefault(key, set()).add(name)
    manager.pinned = pins
    return {"ok": True, "count": sum(len(v) for v in pins.values())}


@app.get("/api/names")
async def api_names():
    return manager.dbc_names


@app.get("/api/dbc/list")
async def api_dbc_list():
    entries = []
    for f in sorted((ROOT / "dbc").rglob("*.dbc")):
        label = f.name
        if f.stem in ("example", "demo_gui"):
            label = f"{f.stem} (demo)"
        rel = str(f.relative_to(ROOT)).replace("\\", "/")
        entries.append({"path": rel, "name": label})
    return {"dbcs": entries}


@app.post("/api/dbc/load")
async def api_dbc_load(payload: dict):
    return manager.load_dbc_file(str(payload.get("path", "")))


@app.get("/api/profiles")
async def api_profiles():
    out = []
    for name in list_profiles():
        try:
            prof = load_profile(name)
            cnt = len(prof.get("annotations") or {})
        except Exception:
            cnt = 0
        out.append({"name": name, "annotations": cnt})
    active = manager.annotations.path.name if manager.annotations.path else None
    return {"profiles": out, "active": active}


@app.get("/api/mcp")
async def api_mcp():
    import importlib.util

    available = importlib.util.find_spec("mcp") is not None
    tools = 0
    if available:
        try:
            from ..mcp_server import TOOL_COUNT

            tools = TOOL_COUNT
        except Exception:  # noqa: BLE001
            tools = 0
    cfg = {"mcpServers": {"mirican-studio": {
        "command": "py", "args": ["-m", "canstudio", "mcp"],
        "env": {"PYTHONPATH": str(ROOT)}}}}
    return {"ok": True, "available": available, "tools": tools,
            "cmd": "py -m canstudio mcp", "config": cfg}


@app.post("/api/profile/load")
async def api_profile_load(payload: dict):
    return manager.load_profile_annotations(str(payload.get("name") or "bmw"))


@app.post("/api/annotation")
async def api_annotation(payload: dict):
    return manager.set_annotation(payload)


def _resolve_log(path: str) -> Path:
    """Ścieżka logu (względna = logs/, dozwolone tylko w katalogu projektu)."""
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / path
        if not p.exists():
            p = LOGS_DIR / path
    p = p.resolve()
    root = ROOT.resolve()
    if root not in p.parents:
        raise ValueError("Plik musi być w katalogu projektu.")
    if not p.exists():
        raise ValueError(f"Nie ma pliku: {path}")
    return p


def _run_autodbc(payload: dict) -> dict:
    """Auto-DBC z wybranego logu → dbc/auto_<nazwa>.dbc (dla panelu Analiza)."""
    try:
        p = _resolve_log(str(payload.get("file", "")))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    messages = read_log(p)
    if not messages:
        return {"ok": False, "error": "Pusty log."}
    groups: dict = {}
    for m in messages:
        ext = bool(getattr(m, "is_extended_id", False))
        key = m.arbitration_id + (0x20000000 if ext else 0)
        g = groups.setdefault(key, {"aid": m.arbitration_id, "ext": ext,
                                    "frames": [], "times": []})
        g["frames"].append(bytes(m.data))
        if getattr(m, "timestamp", None):
            g["times"].append(m.timestamp)
    entries = []
    for g in sorted(groups.values(), key=lambda x: len(x["frames"]), reverse=True)[:24]:
        if len(g["frames"]) < 12:
            continue
        dlc = Counter(len(f) for f in g["frames"]).most_common(1)[0][0]
        frames = [f for f in g["frames"] if len(f) == dlc]
        entries.append({"aid": g["aid"], "ext": g["ext"], "dlc": dlc, "frames": frames,
                        "classes": classify_frames(frames),
                        "period": estimate_period(g["times"]) if len(g["times"]) > 1 else None})
    if not entries:
        return {"ok": False, "error": "Za mało danych na auto-DBC."}
    text = build_dbc(entries, version=__version__, note=p.stem)
    out = ROOT / "dbc" / f"auto_{p.stem}.dbc"
    out.write_text(text, encoding="utf-8")
    return {"ok": True, "file": f"dbc/auto_{p.stem}.dbc", "messages": len(entries)}


@app.get("/api/algos")
async def api_algos():
    return {"algos": [name for name, _ in ALGORITHMS]}


@app.get("/api/logs")
async def api_logs():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    files = sorted(LOGS_DIR.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files[:200]:
        try:
            st = f.stat()
            markers = 0
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if line.startswith("# MARK"):
                        markers += 1
            items.append({"name": f.name, "path": f"logs/{f.name}",
                          "size": st.st_size, "mtime": int(st.st_mtime),
                          "markers": markers})
        except Exception:
            continue
    return {"logs": items, "last_rec": manager.log_name}


@app.post("/api/analyze/quick")
async def api_analyze_quick(payload: dict):
    try:
        path = _resolve_log(str(payload.get("file", "")))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    top = int(payload.get("top", 8))
    messages = read_log(path)
    groups = group_bytes_by_id(messages)
    times: dict = {}
    for m in messages:
        times.setdefault(m.arbitration_id, []).append(m.timestamp)
    order = sorted(groups, key=lambda a: len(groups[a]), reverse=True)[:top]
    out = []
    for aid in order:
        frames = groups[aid]
        result = analyze_frames(frames)
        out.append({
            "id": aid,
            "count": len(frames),
            "dlc": len(frames[0]),
            "period": estimate_period(times[aid]),
            "classes": [{"b": c.byte, "k": c.kind, "d": c.detail}
                        for c in classify_frames(frames)],
            "checksums": [{"b": h.byte, "algo": h.algo, "score": h.score}
                          for h in result.checksums],
            "weak": [{"b": h.byte, "algo": h.algo, "score": h.score}
                     for h in result.weak_checksums[:3]],
        })
    markers = 0
    if path.suffix.lower() == ".log":
        try:
            _, marks = read_candump_with_markers(path)
            markers = len(marks)
        except Exception:
            pass
    return {"ok": True, "file": path.name, "frames": len(messages),
            "markers": markers, "ids": out}


@app.post("/api/analyze/diff")
async def api_analyze_diff(payload: dict):
    try:
        pa = _resolve_log(str(payload.get("file_a", "")))
        pb = _resolve_log(str(payload.get("file_b", "")))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    diffs, only = diff_logs(read_log(pa), read_log(pb),
                            min_frames=int(payload.get("min_frames", 10)),
                            per_id_bytes=6, top_ids=int(payload.get("top", 10)))
    return {
        "ok": True, "a": pa.name, "b": pb.name,
        "ids": [{"id": d.arbitration_id, "n_a": d.n_a, "n_b": d.n_b,
                 "score": round(d.score, 1),
                 "bytes": [{"byte": bd.byte, "mean_a": round(bd.mean_a, 1),
                            "mean_b": round(bd.mean_b, 1), "a": bd.values_a,
                            "b": bd.values_b, "note": bd.note}
                           for bd in d.bytes]}
                for d in diffs],
        "only_a": [{"id": x, "n": n} for x, n in only["A"][:20]],
        "only_b": [{"id": x, "n": n} for x, n in only["B"][:20]],
    }


@app.post("/api/analyze/autodbc")
async def api_analyze_autodbc(payload: dict):
    return await asyncio.to_thread(_run_autodbc, payload)


@app.post("/api/analyze/correlate")
async def api_analyze_correlate(payload: dict):
    try:
        path = _resolve_log(str(payload.get("file", "")))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    messages, marks = read_candump_with_markers(path)
    if not marks:
        return {"ok": False,
                "error": "Ten log nie ma znaczników — nagraj z użyciem ✦ MARK."}
    report = markers_correlate(messages, marks,
                               window_s=float(payload.get("window", 1.5)), top=10)
    return {"ok": True, "file": path.name, "marks": len(marks),
            "labels": [{"label": label, "count": count,
                        "hits": [{"id": c.arbitration_id, "byte": c.byte,
                                  "hits": c.hits, "total": c.total,
                                  "baseline": round(c.baseline, 3)}
                                 for c in cands]}
                       for label, (count, cands) in report.items()]}


@app.post("/api/analyze/button")
async def api_analyze_button(payload: dict):
    try:
        path = _resolve_log(str(payload.get("file", "")))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    label = str(payload.get("label", "przycisk"))
    messages, markers = read_candump_with_markers(path)
    downs: dict = {}
    ups: dict = {}
    for m in markers:
        if not m.label.startswith(label):
            continue
        if "DOWN #" in m.label:
            try:
                downs[int(m.label.split("DOWN #", 1)[1].split()[0])] = m.timestamp
            except (ValueError, IndexError):
                pass
        elif "UP #" in m.label:
            try:
                ups[int(m.label.split("UP #", 1)[1].split()[0])] = m.timestamp
            except (ValueError, IndexError):
                pass
    pairs = sorted((downs[k], ups[k]) for k in downs if k in ups)
    if not pairs:
        return {"ok": False,
                "error": "Brak par znaczników DOWN/UP — uruchom kreator „Sniffer”."}
    hits = find_button(messages, [d for d, _ in pairs], [u for _, u in pairs], top=12)
    return {"ok": True, "file": path.name, "label": label, "pulses": len(pairs),
            "candidates": [
                {"id": h.arbitration_id, "ext": h.ext, "key": h.key,
                 "byte": h.byte, "bit": h.bit, "hits": h.hits,
                 "total": h.total, "returns": h.returns, "delay_ms": h.delay_ms,
                 "delay_spread_ms": h.delay_spread_ms,
                 "baseline": round(h.baseline, 3),
                 "confidence": round(h.confidence, 3),
                 "before": h.before, "held": h.held, "note": h.note}
                for h in hits]}


@app.post("/api/trigger/arm")
async def api_trigger_arm(payload: dict):
    if not manager.connected:
        return {"ok": False, "error": "Brak połączenia."}
    key = int(payload.get("key", 0) or 0)
    byte = int(payload.get("byte", 0) or 0)
    try:
        pre = max(0.5, min(60.0, float(payload.get("pre", 5.0) or 5.0)))
        post = max(0.5, min(60.0, float(payload.get("post", 5.0) or 5.0)))
    except (TypeError, ValueError):
        pre, post = 5.0, 5.0
    keep = bool(payload.get("keep"))
    manager.trigger = {"key": key, "byte": byte, "last": None,
                       "collecting": False, "hit_ts": None,
                       "pre": pre, "post": post, "keep": keep}
    return {"ok": True, "key": key, "byte": byte, "pre": pre, "post": post, "keep": keep}


@app.post("/api/trigger/disarm")
async def api_trigger_disarm():
    manager.trigger = None
    return {"ok": True}


@app.get("/api/mitm/status")
async def api_mitm_status():
    return manager.mitm_status()


@app.post("/api/mitm/start")
async def api_mitm_start(payload: dict):
    return manager.mitm_start(payload)


@app.post("/api/mitm/stop")
async def api_mitm_stop():
    return manager.mitm_stop()


@app.post("/api/uds/scan")
async def api_uds_scan(payload: dict):
    return await asyncio.to_thread(manager.uds_scan, payload)


@app.post("/api/uds/read")
async def api_uds_read(payload: dict):
    return await asyncio.to_thread(manager.uds_read, payload)


@app.post("/api/uds/dtc")
async def api_uds_dtc(payload: dict):
    return await asyncio.to_thread(manager.uds_dtc, payload)


@app.post("/api/uds/write")
async def api_uds_write(payload: dict):
    return await asyncio.to_thread(manager.uds_write, payload)


# ---- OBD (adapter ELM327 / vLinker MS) ------------------------------------

def _resolve_obd_log(file: str) -> Path:
    """Sesja obd_*.jsonl w logs/ projektu (bez sciezek z zewnatrz)."""
    name = Path(str(file or "")).name
    if not name:
        raise ValueError("Nie wybrano pliku.")
    p = (LOGS_DIR / name).resolve()
    root = ROOT.resolve()
    if root not in p.parents:
        raise ValueError("Plik poza projektem.")
    if not name.startswith("obd_") or not name.endswith(".jsonl"):
        raise ValueError("Wybierz plik sesji obd_*.jsonl.")
    if not p.exists():
        raise ValueError(f"Nie ma pliku: {name}")
    return p


def _obd_log_stats(file: str) -> dict:
    try:
        p = _resolve_obd_log(file)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    meta, records = obd_log.parse_session(p)
    out = obd_log.session_stats(records)
    out.update({"ok": True, "file": p.name, "meta": meta})
    return out


def _obd_log_series(file: str, pid: str, max_points: int) -> dict:
    try:
        p = _resolve_obd_log(file)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    _meta, records = obd_log.parse_session(p)
    out = obd_log.series(records, pid, max_points=max_points)
    out.update({"ok": True, "file": p.name})
    return out


@app.post("/api/obd/connect")
async def api_obd_connect(payload: dict):
    return await asyncio.to_thread(_obd().open, payload.get("port") or None)


@app.post("/api/obd/disconnect")
async def api_obd_disconnect():
    await asyncio.to_thread(_obd().close)
    return {"ok": True}


@app.get("/api/obd/status")
async def api_obd_status():
    return _obd().status()


@app.post("/api/obd/read")
async def api_obd_read(payload: dict):
    return await asyncio.to_thread(_obd().read, payload.get("pids") or [])


@app.post("/api/obd/info")
async def api_obd_info():
    return await asyncio.to_thread(_obd().info)


@app.post("/api/obd/dtc")
async def api_obd_dtc(payload: dict):
    return await asyncio.to_thread(_obd().dtc, bool(payload.get("clear")),
                                   bool(payload.get("confirm")))


@app.post("/api/obd/monitor/start")
async def api_obd_monitor_start(payload: dict):
    return await asyncio.to_thread(_obd().monitor_start, payload.get("pids") or [],
                                   float(payload.get("interval") or 0.5),
                                   bool(payload.get("save")))


@app.post("/api/obd/monitor/stop")
async def api_obd_monitor_stop():
    return await asyncio.to_thread(_obd().monitor_stop)


def _obd_pid_rows() -> dict:
    """Lista PID-ow: nasza tabela + to, co wspiera auto (po polaczeniu)."""
    sess = _obd()
    connected = sess.elm is not None
    sup_set = set(sess.supported_pids()) if connected else set()
    rows = []
    for pnum in sorted(set(PID_TABLE) | sup_set):
        ent = PID_TABLE.get(pnum)
        rows.append({"pid": f"01{pnum:02X}",
                     "name": ent[0] if ent else "",
                     "unit": ent[1] if ent else "",
                     "sup": (pnum in sup_set) if connected else None})
    return {"pids": rows,
            "supported": len(sup_set) if connected else None}


@app.get("/api/obd/pids")
async def api_obd_pids():
    return await asyncio.to_thread(_obd_pid_rows)


@app.post("/api/obd/vin")
async def api_obd_vin(payload: dict):
    return decode_vin(str(payload.get("vin") or ""))


@app.get("/api/obd/logs")
async def api_obd_logs():
    return {"logs": obd_log.list_obd_logs()}


@app.post("/api/obd/log/stats")
async def api_obd_log_stats(payload: dict):
    return await asyncio.to_thread(_obd_log_stats, str(payload.get("file") or ""))


@app.post("/api/obd/log/series")
async def api_obd_log_series(payload: dict):
    return await asyncio.to_thread(_obd_log_series, str(payload.get("file") or ""),
                                   str(payload.get("pid") or ""),
                                   int(payload.get("max") or 800))


@app.get("/api/obd/log/config")
async def api_obd_log_config_get():
    return {"ok": True, "config": obd_log.load_logger_config()}


@app.post("/api/obd/log/config")
async def api_obd_log_config_set(payload: dict):
    return {"ok": True, "config": obd_log.save_logger_config(payload or {})}


@app.post("/api/obd/device/manifest")
async def api_obd_device_manifest(payload: dict):
    return await asyncio.to_thread(obd_log.fetch_manifest,
                                   str(payload.get("url") or ""))


@app.post("/api/obd/device/fetch")
async def api_obd_device_fetch(payload: dict):
    return await asyncio.to_thread(obd_log.fetch_file,
                                   str(payload.get("url") or ""),
                                   str(payload.get("name") or ""))


@app.post("/api/log/stats")
async def api_log_stats(payload: dict):
    return await asyncio.to_thread(manager.log_stats, str(payload.get("file", "")))


@app.post("/api/log/trim")
async def api_log_trim(payload: dict):
    return await asyncio.to_thread(manager.log_trim, payload)


@app.post("/api/log/replay/start")
async def api_log_replay_start(payload: dict):
    return manager.log_replay_start(payload)


@app.post("/api/log/replay/stop")
async def api_log_replay_stop():
    return manager.log_replay_stop()


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    global LAST_ACTIVITY
    await websocket.accept()
    CLIENTS.add(websocket)
    LAST_ACTIVITY = time.time()
    try:
        await websocket.send_json({
            "type": "snapshot",
            "status": manager.status(),
            "stats": manager.stats_snapshot(),
            "names": manager.dbc_names,
            "frames": manager.snapshot_frames(),
        })
        while True:
            await websocket.receive_text()  # ignorujemy (keepalive)
    except WebSocketDisconnect:
        pass
    finally:
        CLIENTS.discard(websocket)
        LAST_ACTIVITY = time.time()


# ---------------------------------------------------------------------------
# Uruchomienie
# ---------------------------------------------------------------------------

def _free_port(host: str, start: int, tries: int = 15) -> int:
    import socket
    for candidate in range(start, start + tries):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, candidate))
            return candidate
        except OSError:
            continue
        finally:
            s.close()
    return start


def _warmup_diag() -> None:
    """Wstępne załadowanie modułów diagnostycznych (szybsze 1. połączenie z demo/ECU)."""
    try:
        from .. import diag

        diag.require_deps()
    except Exception:  # noqa: BLE001
        pass


def run(host: str = "127.0.0.1", port: int = 8077, open_browser: bool = True,
        idle_exit: int = 30) -> None:
    global manager, SERVER_REF, IDLE_EXIT, LAST_ACTIVITY
    import uvicorn

    manager = CanManager()
    threading.Thread(target=_warmup_diag, daemon=True).start()
    IDLE_EXIT = max(0, int(idle_exit or 0))
    LAST_ACTIVITY = time.time()
    port = _free_port(host, port)
    url = f"http://{host}:{port}/"
    print(f"# miriCAN Studio v{__version__}: {url}", flush=True)
    if IDLE_EXIT:
        print(f"# Auto-zamknięcie po {IDLE_EXIT}s bez aktywnego GUI "
              "(zwalnia port COM; 0 = wyłączone).", flush=True)
    else:
        print("# Auto-zamknięcie wyłączone.", flush=True)
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    SERVER_REF = uvicorn.Server(config)
    SERVER_REF.run()
    print("# Serwer zatrzymany.", flush=True)
