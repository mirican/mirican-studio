"""Rejestr narzędzi CLI.

Aby dodać nowe narzędzie:
1. utwórz moduł w ``canstudio/tools/`` z atrybutami:
   ``NAME``, ``HELP``, ``add_arguments(parser)`` oraz ``run(args) -> int``,
2. dopisz moduł do listy ``TOOLS`` poniżej.

Narzędzie pojawi się automatycznie w CLI (``py -m canstudio <NAME>``).
"""

from . import (autodbc, bridge, bruteforce, checksum, convert, correlate, ctl,
               diff, discover, gui, mcp, obd, ports, proc, profile, replay, scan,
               selftest, send, sniff, stats, uds, vin, watch)

TOOLS = [gui, sniff, watch, scan, send, replay, bridge, bruteforce, diff,
         correlate, checksum, discover, autodbc, stats, convert, profile, ports,
         proc, selftest, uds, obd, vin, ctl, mcp]
