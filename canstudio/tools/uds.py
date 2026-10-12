"""Narzędzie: uds — diagnostyka UDS/ISO-TP (skan ECU, DID, DTC, sesje).

Uruchamiaj z głową: UDS **wysyła ramki** na magistralę — tylko postój lub ławka.
"""

from __future__ import annotations

import argparse
import sys

from ..bus import add_bus_args, open_bus
from ..json_cli import add_json_args, emit, json_mode

NAME = "uds"
HELP = ("Diagnostyka UDS/ISO-TP: skan ECU, odczyt/zapis DID, kody DTC, "
        "sesje diagnostyczne (wymaga: pip install can-isotp udsoncan)")

BANNER = (
    "# UWAGA: UDS wysyła ramki na magistralę — tylko postój lub ławka testowa;\n"
    "# nie wolno nadawać na magistralach poduszek/hamulców/kierownicy. Każda\n"
    "# wysyłka trafia do logu w katalogu logs/."
)

#: Usługi, których wywołanie może zmieniać stan sterownika (wymagają --yes w `raw`).
DANGEROUS_SIDS = {0x11, 0x14, 0x27, 0x28, 0x2E, 0x2F, 0x31, 0x34, 0x35, 0x36,
                  0x37, 0x38, 0x85}


def _diag():
    from .. import diag

    diag.require_deps()
    return diag


def _banner() -> None:
    print(BANNER)


def _get_ids(args):
    """(txid, rxid) z argumentów; domyślnie rxid = txid + 8."""
    diag = _diag()
    if not getattr(args, "txid", None):
        raise SystemExit("Podaj --txid (ID sterownika, np. --txid 6F1)")
    tx = diag.parse_hex(args.txid)
    if getattr(args, "rxid", None):
        rx = diag.parse_hex(args.rxid)
    else:
        rx = tx + 8
        print(f"# rxid nie podano -> 0x{rx:X} (txid + 8, typowy offset odpowiedzi)")
    return tx, rx


def _open_session(args, log_prefix="uds"):
    """Otwiera magistralę + ISO-TP + klienta UDS. Zwraca słownik-zasoby."""
    diag = _diag()
    _banner()
    tx, rx = _get_ids(args)
    bus = open_bus(args)
    tp = diag.open_isotp(bus, tx, rx, extended=bool(getattr(args, "ext", False)))
    log = diag.open_log(log_prefix)
    log.note(f"txid=0x{tx:X} rxid=0x{rx:X} ext={bool(getattr(args, 'ext', False))}")
    client, conn = diag.make_client(tp, log)
    print(f"# ISO-TP: 0x{tx:X} -> 0x{rx:X}   (log: {log.path})")
    return {"diag": diag, "bus": bus, "tp": tp, "conn": conn, "client": client, "log": log}


def _close(sess) -> None:
    sess["log"].close()
    sess["diag"].close_session(sess["bus"], sess["tp"], sess["conn"])


def _maybe_session(sess, session) -> None:
    """Opcjonalne wejście w sesję diagnostyczną przed komendą."""
    if session is None:
        return
    r = sess["client"].change_session(int(session))
    if r.positive:
        print(f"# sesja 0x{int(session):02X}: OK")
    else:
        print(f"# sesja 0x{int(session):02X}: ODMOWA ({sess['diag'].code_name(r.code)})")


def _print_did_resp(diag, did: int, r) -> dict:
    name = diag.did_name(did)
    label = f" ({name})" if name else ""
    tag = f"[0x{did:04X}]{label}"
    info = {"did": did, "name": name or "", "positive": bool(r.positive)}
    if not r.positive:
        info["code"] = diag.code_name(r.code)
        print(f"{tag}: NEGATYWNIE — {diag.code_name(r.code)}")
        return info
    value = diag.did_value(r, did)
    if isinstance(value, (bytes, bytearray)):
        info["hex"] = bytes(value).hex(" ").upper()
        print(f"{tag}: {diag.fmt_bytes(bytes(value))}")
    else:
        info["value"] = str(value)
        print(f"{tag}: {value}")
    return info


# ---------------------------------------------------------------------------
# Podkomendy
# ---------------------------------------------------------------------------

def cmd_scan(args) -> int:
    json_mode(args)
    diag = _diag()
    _banner()
    ids = diag.parse_ids_spec(args.ids)
    probe = diag.parse_hex_bytes(args.probe)
    print(f"# skan ECU: {len(ids)} adresów (0x{ids[0]:X}..0x{ids[-1]:X}), offset +{args.offset}, "
          f"próbka {' '.join(f'{b:02X}' for b in probe)}, timeout {args.timeout * 1000:.0f} ms")
    if getattr(args, "silent", False):
        print("# uwaga: tryb silent (bez ACK) — sterowniki mogą nie odpowiadać na wysyłkę")
    bus = open_bus(args)
    log = diag.open_log("uds_scan")
    found = []

    def on_result(res):
        found.append(res)
        for txid, rxid, payload in [(res["txid"], res["rxid"], res["resp"])]:
            if payload is not None:
                sys.stdout.write(
                    f"\r  0x{txid:03X} -> 0x{rxid:03X}: {diag.fmt_bytes(payload)}\n")
        for can_id, payload in res["others"][:3]:
            sys.stdout.write(
                f"\r  0x{res['txid']:03X}: możliwa odpowiedź z 0x{can_id:03X}: "
                f"{diag.fmt_bytes(payload)}\n")
        sys.stdout.flush()

    def on_progress(i, total):
        sys.stdout.write(f"\r# postęp: {i}/{total}…" + " " * 8)
        sys.stdout.flush()

    try:
        results = diag.scan_ecus(bus, ids, offset=args.offset, probe=probe,
                                 timeout=args.timeout, extended=bool(args.ext),
                                 on_progress=on_progress, on_result=on_result, log=log)
        found = [r for r in results if r["resp"] is not None or r["others"]]
    except KeyboardInterrupt:
        print("\n# przerwano przez użytkownika")
    finally:
        bus.shutdown()

    sys.stdout.write("\n")
    hits = [r for r in found if r["resp"] is not None]
    print(f"# wynik: {len(hits)} odpowiedzi (z {len(ids)} sprawdzonych adresów)")
    for res in hits:
        print(f"  + 0x{res['txid']:03X} -> 0x{res['rxid']:03X}: {diag.fmt_bytes(res['resp'])}")
    if not hits:
        print("# brak odpowiedzi. Co sprawdzić:")
        print("#  - zakres/offset ID (--ids 6F1,6F9 / --range 600-6FF / --offset 8)")
        print("#  - inne ID odpowiedzi niż +8 -> spójrz na linie 'możliwa odpowiedź'")
        print("#  - próbka inna niż TesterPresent: --probe 1001 (default session)")
        print("#  - bitrate (--profile bmw), kable, zapłon; bramka może filtrować")
    if getattr(args, "json", False):
        emit({"ok": True, "checked": len(ids),
              "found": [{"txid": r["txid"], "rxid": r["rxid"],
                         "payload": " ".join(f"{b:02X}" for b in r["resp"])}
                        for r in hits]})
    print(f"# log: {log.path}")
    log.close()
    return 0


def cmd_info(args) -> int:
    json_mode(args)
    diag = _diag()
    dids = (diag.parse_ids_spec(args.dids) if args.dids else list(diag.INFO_DIDS))
    sess = _open_session(args, "uds_info")
    jdids = []
    try:
        _maybe_session(sess, diag.parse_hex(args.session) if args.session else None)
        for did in dids:
            r = sess["client"].read_data_by_identifier(did)
            jdids.append(_print_did_resp(diag, did, r))
    finally:
        _close(sess)
    if getattr(args, "json", False):
        emit({"ok": True, "dids": jdids})
    return 0


def cmd_read(args) -> int:
    json_mode(args)
    diag = _diag()
    dids = [diag.parse_hex(x) for x in args.dids]
    sess = _open_session(args, "uds_read")
    jdids = []
    try:
        _maybe_session(sess, diag.parse_hex(args.session) if args.session else None)
        for did in dids:
            r = sess["client"].read_data_by_identifier(did)
            jdids.append(_print_did_resp(diag, did, r))
    finally:
        _close(sess)
    if getattr(args, "json", False):
        emit({"ok": True, "dids": jdids})
    return 0


def cmd_write(args) -> int:
    json_mode(args)
    diag = _diag()
    if not args.yes:
        raise SystemExit("Zapis DID modyfikuje sterownik. Jeśli wiesz, co robisz: dodaj --yes")
    did = diag.parse_hex(args.did)
    data = diag.parse_hex_bytes(args.data)
    sess = _open_session(args, "uds_write")
    r = None
    try:
        _maybe_session(sess, diag.parse_hex(args.session) if args.session else None)
        r = sess["client"].write_data_by_identifier(did, data)
        if r.positive:
            print(f"[0x{did:04X}] zapis OK: {diag.fmt_bytes(data)}")
        else:
            print(f"[0x{did:04X}] ODMOWA: {diag.code_name(r.code)}")
    finally:
        _close(sess)
    if getattr(args, "json", False) and r is not None:
        emit({"ok": bool(r.positive), "did": did, "written": data.hex(" ").upper(),
              "code": None if r.positive else diag.code_name(r.code)})
    return 0


def cmd_dtc(args) -> int:
    json_mode(args)
    diag = _diag()
    mask = diag.parse_hex(args.mask)
    sess = _open_session(args, "uds_dtc")
    jdtcs = []
    jcleared = None
    jok = True
    try:
        _maybe_session(sess, diag.parse_hex(args.session) if args.session else None)
        r = sess["client"].get_dtc_by_status_mask(mask)
        if r.positive:
            sd = r.service_data
            dtcs = list(getattr(sd, "dtcs", []) or [])
            count = getattr(sd, "dtc_count", None)
            jdtcs = [{"id": d.id, "text": diag.fmt_dtc(d)} for d in dtcs]
            print(f"# DTC: {count if count is not None else len(dtcs)} (mask 0x{mask:02X})")
            for d in dtcs:
                print(f"  {diag.fmt_dtc(d)}")
            if not dtcs:
                print("  (brak zapisanych błędów)")
            if getattr(r, "data", None):
                print(f"# raw: {diag.fmt_bytes(bytes(r.data))}")
        else:
            jok = False
            print(f"# odczyt DTC: ODMOWA — {diag.code_name(r.code)}")
        if args.clear:
            if not args.yes:
                raise SystemExit("--clear usuwa kody błędów. Dodaj --yes aby potwierdzić.")
            r2 = sess["client"].clear_dtc()
            jcleared = bool(r2.positive)
            print("# kasowanie DTC: " + ("OK" if r2.positive else
                                         f"ODMOWA — {diag.code_name(r2.code)}"))
    finally:
        _close(sess)
    if getattr(args, "json", False):
        emit({"ok": jok, "mask": mask, "dtcs": jdtcs, "cleared": jcleared})
    return 0


def cmd_session(args) -> int:
    json_mode(args)
    diag = _diag()
    value = diag.parse_hex(args.type)
    sess = _open_session(args, "uds_session")
    jok = False
    try:
        r = sess["client"].change_session(value)
        jok = bool(r.positive)
        if r.positive:
            extra = f" — {diag.fmt_bytes(bytes(r.data))}" if getattr(r, "data", None) else ""
            print(f"# sesja 0x{value:02X}: OK{extra}")
            print("# uwaga: sesja wygasa po rozłączeniu (S3); w kolejnych komendach "
                  "użyj --session 0x%02X" % value)
        else:
            print(f"# sesja 0x{value:02X}: ODMOWA — {diag.code_name(r.code)}")
    finally:
        _close(sess)
    if getattr(args, "json", False):
        emit({"ok": jok, "session": value})
    return 0


def cmd_reset(args) -> int:
    json_mode(args)
    diag = _diag()
    if not args.yes:
        raise SystemExit("Reset restartuje sterownik. Jeśli to zamierzone: dodaj --yes")
    value = diag.parse_hex(args.type)
    sess = _open_session(args, "uds_reset")
    jok = False
    try:
        r = sess["client"].ecu_reset(value)
        jok = bool(r.positive)
        print(f"# reset 0x{value:02X}: " + ("OK" if r.positive else
                                            f"ODMOWA — {diag.code_name(r.code)}"))
        print("# sterownik może milczeć kilka sekund po resecie")
    finally:
        _close(sess)
    if getattr(args, "json", False):
        emit({"ok": jok, "reset": value})
    return 0


def cmd_raw(args) -> int:
    json_mode(args)
    diag = _diag()
    payload = diag.parse_hex_bytes(args.payload)
    if not payload:
        raise SystemExit("Pusty payload")
    sid = payload[0]
    if sid in DANGEROUS_SIDS and not args.yes:
        raise SystemExit(
            f"Usługa 0x{sid:02X} może zmieniać stan sterownika — dodaj --yes jeśli "
            "jesteś pewien (tylko postój/ławka).")
    sess = _open_session(args, "uds_raw")
    timeout = args.timeout if args.timeout > 0 else 2.0
    jresp = None
    try:
        conn = sess["conn"]
        print(f">> {diag.fmt_bytes(payload)}")
        conn.send(payload)
        while True:
            resp = conn.wait_frame(timeout=timeout)
            if resp is None:
                print("# brak odpowiedzi (timeout)")
                break
            jresp = bytes(resp)
            print(f"<< {diag.fmt_bytes(resp)}")
            if len(resp) >= 3 and resp[0] == 0x7F and resp[2] == 0x78:
                print("# ...responsePending - czekam dalej")
                continue
            if resp[0] == 0x7F and len(resp) >= 3:
                print(f"# NRC: {diag.code_name(resp[2])}")
            break
    finally:
        _close(sess)
    if getattr(args, "json", False):
        emit({"ok": True, "request": payload.hex(" ").upper(),
              "response": jresp.hex(" ").upper() if jresp is not None else None})
    return 0


# ---------------------------------------------------------------------------
# Rejestracja
# ---------------------------------------------------------------------------

def _add_common(p: argparse.ArgumentParser) -> None:
    add_bus_args(p)
    p.add_argument("--profile", help="profil pojazdu z profiles/ (ustawia bitrate)")
    p.add_argument("--txid", help="ID żądania w hex (np. 6F1)")
    p.add_argument("--rxid", help="ID odpowiedzi w hex (domyślnie txid+8)")
    p.add_argument("--ext", action="store_true", help="adresowanie 29-bit")
    add_json_args(p)


def _add_session_opt(p: argparse.ArgumentParser) -> None:
    p.add_argument("--session", help="wejście w sesję diagnostyczną przed komendą "
                                     "(hex, np. 3 = extended)")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="tryb", metavar="<tryb>")
    parser.set_defaults(_cmd=None)

    p = sub.add_parser("scan", help="skaner ECU — szuka sterowników odpowiadających na magistrali")
    _add_common(p)
    p.add_argument("--ids", default="600-6FF",
                   help="adresy do sprawdzenia: '600-6FF' lub '6F1,6F3' (domyślnie 600-6FF)")
    p.add_argument("--offset", type=int, default=8,
                   help="oczekiwany offset odpowiedzi: rxid = txid + offset (domyślnie 8)")
    p.add_argument("--probe", default="3E00",
                   help="payload próbki w hex (domyślnie 3E00 = TesterPresent)")
    p.add_argument("--timeout", type=float, default=0.05,
                   help="czas oczekiwania na odpowiedź na 1 adres [s] (domyślnie 0.05)")
    p.set_defaults(_cmd=cmd_scan)

    p = sub.add_parser("info", help="szybkie rozpoznanie sterownika (VIN, numer seryjny, wersje…)")
    _add_common(p)
    _add_session_opt(p)
    p.add_argument("--dids", help="własna lista DID w hex (np. F190,F18C)")
    p.set_defaults(_cmd=cmd_info)

    p = sub.add_parser("read", help="odczyt DID (ReadDataByIdentifier)")
    _add_common(p)
    _add_session_opt(p)
    p.add_argument("dids", nargs="+", help="identyfikatory DID w hex (np. F190)")
    p.set_defaults(_cmd=cmd_read)

    p = sub.add_parser("write", help="zapis DID (WriteDataByIdentifier) — wymaga --yes")
    _add_common(p)
    _add_session_opt(p)
    p.add_argument("did", help="identyfikator DID w hex")
    p.add_argument("data", help="dane w hex (np. '01 02 FF')")
    p.add_argument("--yes", action="store_true", help="potwierdź zapis (modyfikuje sterownik)")
    p.set_defaults(_cmd=cmd_write)

    p = sub.add_parser("dtc", help="odczyt (i opcjonalnie kasowanie) kodów błędów DTC")
    _add_common(p)
    _add_session_opt(p)
    p.add_argument("--mask", default="FF", help="status mask w hex (domyślnie FF = wszystkie)")
    p.add_argument("--clear", action="store_true", help="skasuj DTC po odczytaniu (wymaga --yes)")
    p.add_argument("--yes", action="store_true", help="potwierdź kasowanie DTC")
    p.set_defaults(_cmd=cmd_dtc)

    p = sub.add_parser("session", help="ustaw sesję diagnostyczną (0x10)")
    _add_common(p)
    p.add_argument("type", help="typ sesji w hex: 1=default, 2=programming, 3=extended")
    p.set_defaults(_cmd=cmd_session)

    p = sub.add_parser("reset", help="reset sterownika (0x11) — wymaga --yes")
    _add_common(p)
    p.add_argument("--type", default="1", help="typ resetu w hex (domyślnie 1 = hard reset)")
    p.add_argument("--yes", action="store_true", help="potwierdź reset (restartuje sterownik)")
    p.set_defaults(_cmd=cmd_reset)

    p = sub.add_parser("raw", help="surowa komenda UDS (eksploracja; usługi modyfikujące: --yes)")
    _add_common(p)
    p.add_argument("payload", help="payload w hex, np. '22 F1 90'")
    p.add_argument("--timeout", type=float, default=2.0, help="timeout odpowiedzi [s]")
    p.add_argument("--yes", action="store_true", help="potwierdź jeśli usługa modyfikuje stan")
    p.set_defaults(_cmd=cmd_raw)


def run(args) -> int:
    fn = getattr(args, "_cmd", None)
    if fn is None:
        print("Użyj: py -m canstudio uds {scan|info|read|write|dtc|session|reset|raw} …")
        print("Szczegóły: py -m canstudio uds -h")
        return 1
    return fn(args)
