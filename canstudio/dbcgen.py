"""Auto-DBC — generator wstępnego pliku DBC z logu (lub nasłuchu).

Na podstawie klasyfikacji bajtów (``detect.classify_frames``) buduje plik DBC,
w którym każdy bajt ramki jest osobnym sygnałem z nazwą wg klasy:
``const`` / ``counter`` / ``checksum`` / ``switch`` / ``sensor`` / ``var`` / ``mix``.
Dzięki temu surowe logi można od razu dekodować w GUI (Sygnały / DBC)
i w cantools — bez ręcznego pisania DBC.

Komentarze w DBC celowo po angielsku/ASCII (DBC bywa czytane jako cp1250,
a tak plik jest przenośny).
"""

from __future__ import annotations

import re
from datetime import datetime

#: klasa bajtu -> sufiks nazwy sygnału
_SUFFIX = {
    "licznik": "counter",
    "suma": "checksum",
    "stały": "const",
    "przełącznik/zdarzenie": "switch",
    "sensor": "sensor",
    "zmienny": "var",
    "mieszany": "mix",
}

_SAFE = re.compile(r"[^A-Za-z0-9_]")


def kind_label(kind: str) -> str:
    """Klasa bajtu (PL) -> sufiks/etykieta sygnału."""
    return _SUFFIX.get(kind, "mix")


def safe_ident(name: str, fallback: str = "X") -> str:
    """Nazwa zgodna z identyfikatorem DBC."""
    s = _SAFE.sub("_", str(name)).strip("_")
    if not s or s[0].isdigit():
        s = "X_" + s
    return s or fallback


def build_dbc(entries: list[dict], *, version: str = "1.2", note: str = "") -> str:
    """Buduje tekst DBC.

    ``entries``: lista dictów:
      ``aid`` (int), ``ext`` (bool), ``dlc`` (int), ``frames`` (list[bytes]),
      ``classes`` (list[ByteClass] z detect), ``period`` (float|None, sekundy),
      ``name`` (str|None — własna nazwa wiadomości).
    """
    if not entries:
        raise ValueError("brak ID do wygenerowania DBC")

    lines: list[str] = []
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f'VERSION "canstudio auto-DBC {version} ({stamp}){(" - " + note) if note else ""}"')
    lines.append("")
    lines.append("NS_ :")
    for ns in ("NS_DESC_", "CM_", "BA_DEF_", "BA_", "VAL_", "CAT_DEF_", "CAT_",
               "FILTER", "BA_DEF_DEF_", "EV_DATA_", "ENVVAR_DATA_", "SGTYPE_",
               "SGTYPE_VAL_", "BA_DEF_SGTYPE_", "BA_SGTYPE_", "SIG_TYPE_REF_",
               "VAL_TABLE_", "SIG_GROUP_", "SIG_VALTYPE_", "SIGTYPE_VALTYPE_",
               "BO_TX_BU_", "BA_DEF_REL_", "BA_REL_", "BA_DEF_DEF_REL_",
               "BU_SG_REL_", "BU_EV_REL_", "BU_BO_REL_", "SG_MUL_VAL_"):
        lines.append("\t" + ns)
    lines.append("")
    lines.append("BS_:")
    lines.append("")
    lines.append("BU_: Vector__XXX")
    lines.append("")

    sig_defs: list[str] = []
    comments: list[str] = []

    for entry in entries:
        aid = int(entry["aid"])
        ext = bool(entry.get("ext"))
        dlc = int(entry["dlc"])
        frames = entry["frames"]
        classes = entry["classes"]
        period = entry.get("period")
        did = (aid | 0x80000000) if ext else aid
        name = safe_ident(entry.get("name") or (f"MSG_{aid:08X}" if ext else f"MSG_{aid:03X}"))
        lines.append(f"BO_ {did} {name}: {dlc} Vector__XXX")

        class_by_byte = {c.byte: c for c in classes}
        sample = frames[0] if frames else b""
        for i in range(dlc):
            c = class_by_byte.get(i)
            suffix = kind_label(c.kind) if c else "mix"
            sig = f"b{i}_{suffix}"
            start = 8 * i  # pełny bajt jako sygnał (zweryfikowane z cantools: @1, 8*i)
            lo, hi = 0, 255
            val = sample[i] if i < len(sample) else 0
            if c and c.kind == "stały":
                lo = hi = val
            lines.append(f' SG_ {sig} : {start}|8@1+ (1,0) [{lo}|{hi}] "" Vector__XXX')

            if c and c.kind != "stały":
                detail = f"class: {kind_label(c.kind)}"
                if c.detail:
                    detail += f" ({c.detail})"
                sig_defs.append(f'CM_ SG_ {did} {sig} "{detail}";')
            elif c:
                sig_defs.append(f'CM_ SG_ {did} {sig} "const value 0x{val:02X}";')

        summary_parts = []
        for c in classes:
            summary_parts.append(f"b{c.byte}={kind_label(c.kind)}")
        meta = f"auto-DBC: frames={len(frames)}"
        if period:
            meta += f", period~{period * 1000:.1f}ms ({1.0 / period:.1f}Hz)"
        if summary_parts:
            meta += "; " + ", ".join(summary_parts)
        if ext:
            meta += "; 29-bit"
        comments.append(f'CM_ BO_ {did} "{meta}";')

    lines.append("")
    lines.extend(comments)
    lines.extend(sig_defs)
    lines.append("")
    return "\n".join(lines)
