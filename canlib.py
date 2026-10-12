"""canlib - shim zgodnościowy (stary interfejs).

Nowy kod powinien używać pakietu ``canstudio``:
``from canstudio.bus import open_bus`` itd. Ten moduł istnieje tylko po to,
żeby stare skrypty (``from canlib import ...``) dalej działały.
"""

from canstudio.bus import (Canable2SlcanBus, add_bus_args, open_bus,  # noqa: F401
                           serial_ports)
from canstudio.dbc import decode_into, load_dbc  # noqa: F401
from canstudio.frames import (Frame, format_frame, message_from_frame,  # noqa: F401
                              parse_frame_line, parse_id, parse_ids)
from canstudio.stats import IdStats  # noqa: F401

__all__ = [
    "Canable2SlcanBus", "add_bus_args", "open_bus", "serial_ports",
    "decode_into", "load_dbc",
    "Frame", "format_frame", "message_from_frame", "parse_frame_line",
    "parse_id", "parse_ids",
    "IdStats",
]
