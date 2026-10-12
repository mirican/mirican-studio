# 06 — Auto-DBC (wstępny plik .dbc z logu / nasłuchu)

`autodbc` buduje plik DBC na podstawie klasyfikacji bajtów — każdy bajt ramki staje się
sygnałem z nazwą wg klasy: `counter` (licznik), `checksum` (suma), `switch` (przełącznik/
zdarzenie), `sensor`, `const` (stały), `var`, `mix`. Dzięki temu świeży log z nieznanego
auta można od razu dekodować w GUI i w cantools — bez ręcznego pisania DBC.

## Komendy

```powershell
py -m canstudio autodbc logs\sniff_20261007.log                 # z logu -> dbc/auto_<nazwa>.dbc
py -m canstudio autodbc logs\sniff_20261007.log --ids 0x130,0x2CA
py -m canstudio autodbc --capture 15 --channel COM7 --profile bmw   # 15 s nasłuchu na żywo
py -m canstudio autodbc log.log --out dbc\moj_uklad.dbc --top 40 --min-frames 20
```

Przykładowy wynik:

```
  0x130: b0 const, b1 counter, b2 switch, b3 sensor, b4 sensor, b5 sensor, b6 const, b7 checksum, ~20.0 ms
  0x2CA: b0 counter, b1 const, b2 const, b3 const, ~50.0 ms
```

Generowany plik przechodzi walidację (cantools wczytuje i dekoduje ostatnią ramkę każdego ID).

## Jak używać dalej

- **GUI**: wczytaj `auto_*.dbc` w sekcji DBC — nowe pliki pojawiają się na liście od razu.
  Sygnały widać w Inspektorze, a przypięte (＋) lądują na wykresie.
- **CLI**: `py -m canstudio sniff --channel COM7 --dbc dbc\auto_<nazwa>.dbc`
- Kolumny metadanych w komentarzach: liczba ramek, okres [ms], klasy bajtów, znacznik 29-bit.

## Uwagi

- Sygnały to pojedyncze bajty (`b0…b7`, 8-bit) — to mapa surowa, nie fizyczne jednostki.
  Nazwy mówią tylko, jak bajt się zachowuje.
- Komentarze w pliku są po angielsku/ASCII (DBC bywa czytane jako cp1250 — tak jest przenośne).
- To punkt startowy: nazwy/klasy można dopisywać ręcznie, a po sesji z autem warto podmienić
  plik na właściwy DBC producenta (np. z `dbc/opendbc`).
- Przykłady wygenerowane z logów demo: `dbc/auto_demo_b.dbc`, `dbc/auto_demo_markers.dbc`.
