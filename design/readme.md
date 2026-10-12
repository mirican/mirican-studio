# design/ — makiety miriCAN Studio

## `can-studio-mockup.html`

Statyczna makieta interfejsu CAN Studio (dane demonstracyjne, bez backendu).

**Jak otworzyć:** dwuklik na pliku albo w przeglądarce:

```
file:///<ścieżka do projektu>/can-toolkit/design/can-studio-mockup.html
```

**Co można klikać:**
* `PAUZA/START` (lub spacja) — zatrzymuje/wznawia „ruch" na magistrali,
* `REC` (lub R) — symulacja nagrywania (pojawia się nazwa pliku logu),
* przełącznik kręgów w prawym górnym rogu — **3 kierunki wizualne**:
  * **A · bursztyn** (warsztat) — domyślny,
  * **B · fosfor** (oscyloskop),
  * **C · lód** (serwis),
* klik w wiersz ramki — panel „ID Insight" (sygnały, licznik, suma).

**Status (2026-10-06):** makieta zrealizowana jako **działające GUI** —
uruchom `GUI.bat` albo `py -m canstudio gui` (live trace, TX, REC, tryb demo).

**Do decyzji:** co dalej w GUI? (panele diff/checksum, konfigurator MITM,
wykresy wielu sygnałów naraz).
