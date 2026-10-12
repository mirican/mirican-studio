# Man in the middle (MITM) na magistrali CAN

## Koncepcja

MITM = „wpięcie się w środek" magistrali: urządzenie z **dwoma kanałami CAN**
siedzi między dwoma segmentami (np. gateway a modułem) i:

* przekazuje ramki w obie strony (jak przedłużacz),
* może je filtrować, modyfikować, dokładać własne,
* loguje wszystko, co przechodzi.

Po co: podmiana pojedynczych bajtów „w locie", wstrzykiwanie komend bez
odpinania modułu, podsłuch ruchu między modułami.

## Wymagania sprzętowe

Fizyczny MITM wymaga **dwóch niezależnych interfejsów CAN**:

* 2 × Canable (nasz MKS + drugi adapter), albo
* jedna płytka dwukanałowa (ESP32 + 2× transceiver, dual-CAN HAT).

Na jednym kanale MITM nie istnieje (nie da się być jednocześnie po dwóch
stronach magistrali). Softwarowo wszystko jest gotowe — po podłączeniu
drugiego adaptera wystarczy wskazać go w `--out`.

## Nasz silnik: `py -m canstudio bridge`

### Tryby

* **MITM** (domyślnie): przekazuje ramki A↔B.
* **`--tap`**: tylko podgląda i loguje (bez przekazywania) — bezpieczny start.
* **Demo bez sprzętu**: `py -m canstudio bridge --demo` — magistrale wirtualne;
  pokazuje w akcji modyfikację bajtu, prowadzenie licznika i przeliczanie sumy.

### Reguły (CLI)

| opcja | znaczenie |
|---|---|
| `--set "ID:BYTE=VALUE"` | ustaw bajt w przekazywanej ramce |
| `--counter "ID:BYTE"` | prowadź licznik +1 dla każdej przekazanej ramki tego ID |
| `--checksum "ID:BYTE:ALGO"` | automatycznie przeliczaj sumę (algo np. `xor8`) |
| `--drop "ID,ID"` | nie przekazuj tych ID |
| `--rules plik.json` | reguły w pliku JSON (schema niżej) |

Przykład — podmiana bajtu z automatyczną naprawą licznika i sumy:

```
py -m canstudio bridge --in slcan:COM7 --out slcan:COM8 ^
   --set "0x130:3=0x2A" --counter "0x130:1" --checksum "0x130:7:xor8"
```

### Reguły w pliku (JSON)

```json
{
  "drop":     ["0x2C0"],
  "set":      [{"id": "0x130", "byte": 3, "value": 42}],
  "counter":  [{"id": "0x130", "byte": 1}],
  "checksum": [{"id": "0x130", "byte": 7, "algo": "xor8"}]
}
```

## Jak to wpina się w resztę programu

* **Sumy kontrole** — te same algorytmy co w `canstudio checksum`:
  najpierw wykryj (`checksum`), potem użyj w regułach (`bridge --checksum`).
* **Liczniki** — `checksum` wskaże bajt-licznik; podajesz go w `--counter`.
* **Diff / correlate** — do ustalenia, *który* bajt w ogóle warto podmieniać.
* **GUI (w przygotowaniu)** — konfigurator reguł + podgląd obu stron ruchu.

## Bezpieczeństwo

* MITM **przekazuje ruch na żywo** — używaj na stole / w warsztacie, nie w trasie.
* Zacznij od `--tap` (podgląd), potem włączaj przekazywanie.
* Log (`logs/bridge_*.log`) zawiera obie strony ruchu — dobry materiał do
  dalszej analizy (`diff`, `discover`, `correlate`).
