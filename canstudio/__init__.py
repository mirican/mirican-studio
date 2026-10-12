"""miriCAN Studio - zestaw narzędzi do pracy z magistralą CAN.

Pakiet modularny:
* ``canstudio.bus``      - wybór/otwieranie magistrali (rejestr interfejsów),
* ``canstudio.frames``   - model ramki + format/parsowanie candump,
* ``canstudio.logio``    - odczyt/zapis logów (candump, .asc, .blf),
* ``canstudio.dbc``      - dekodowanie DBC (cantools),
* ``canstudio.checksums``- detekcja liczników i sum kontrolnych,
* ``canstudio.diffing``  - porównywanie nagrań,
* ``canstudio.diag``     - diagnostyka UDS/ISO-TP (can-isotp + udsoncan),
* ``canstudio.tools``    - narzędzia CLI (sniff, send, replay, scan, uds, diff, ...).

Uruchamianie: ``py -m canstudio <narzędzie> [opcje]``
"""

__version__ = "2.4"
