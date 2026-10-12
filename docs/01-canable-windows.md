# MKS CANable 2.0 PRO — sprzęt i tryby pracy (Windows)

## Co mamy

* **MKS CANable 2.0 PRO** — izolowany USB→CAN, obsługuje CAN-FD
  (STM32G431; wersja PRO ma izolację CAN↔USB).
  Produkt: https://makerbase3d.com/product/makerbase-canable-v2/
  Źródła: https://github.com/makerbase-mks/CANable-MKS
* Nasz egzemplarz (ustalenia z 2026-10-05):
  * firmware **normaldotcom/canable2** (https://github.com/normaldotcom/canable2-fw),
    tryb **slcan**
  * USB: `VID:PID = 16D0:117E`, opis urządzenia: `CANable2 ... canable2.git`
  * port: **COM7** (może się zmienić — sprawdzaj `py sniff.py --list-ports`)
  * komenda `V` zwraca wersję firmware (np. `16e7497-dirty github.com/normaldotcom/canable2.git`)
  * otwieranie przez python-can (`slcan`) — przetestowane ✅

## Tryb slcan (obecny, zalecany na start)

Zero sterowników (CDC-ACM), działa od razu na Windows/Linux.
Obsługiwane komendy (skrót z README firmware):

| komenda | znaczenie |
|---|---|
| `S0..S8` | bitrate: 10k, 20k, 50k, 100k, 125k, **250k**, **500k**, 750k, 1M |
| `S9` | 83.3k |
| `Y2` / `Y5` | data bitrate CAN-FD: 2M / 5M |
| `M0` / `M1` | tryb normalny / **silent (nasłuch bez ACK)** |
| `O` / `C` | otwórz / zamknij kanał |
| `A0` / `A1` | auto-retransmisja off / on |
| `t..T` / `d..D` / `b..B` | nadawanie ramek (klasyczne / FD / FD+BRS) |

Uwagi:
* **Tryb silent to `M1`** — standardowa komenda `L` z Lawicel **nie jest**
  obsługiwana przez ten firmware. Nasze skrypty robią to poprawnie
  (`--silent`; klasa `Canable2SlcanBus` w `canlib.py`).
* Kolejność: konfiguracja (S/Y/M) → `O` → nadawanie.
* Firmware nie potwierdza komend (brak ACK/NACK na serialu).
* RAMKI CAN-FD: firmware obsługuje (Y2/Y5 + `d/D/b/B`), python-can `slcan`
  ma częściowe wsparcie (data bitrate 2M/5M, `timing=BitTimingFd`).

## Tryb candlelight (gs_usb) — opcjonalny

Daje „natywne" gs_usb / SocketCAN (Linux plug&play), część rzeczy jest
wygodniejsza, ale **na Windows wymaga sterownika WinUSB (Zadig) + pyusb**.

Na MKS CANable 2.0 PRO działa wersja z gałęzi **multichannel** projektu
candleLight (target `CANable2_MKS_fw`); mainline jeszcze tej płytki nie
wspiera. Instrukcja: https://github.com/SebKuzminsky/mks-canable-2.0-pro

Flashowanie (ogólnie):
1. Zworka/ przycisk **BOOT** → podłącz USB (device: `0483:df11` DFU).
2. Wgraj `.bin` (dfu-util / `make flash-...`).
3. Odłącz, zdejmij BOOT, podłącz — enumeracja: `1d50:606f` (candleLight).

* Oryginalny CANable 2.0 ma web-updater w Chrome: https://canable.io/updater/canable2.html
* Poradnik dla klonów MKS (także slcan ↔ candlelight): https://maz0r.github.io/klipper_canbus/controller/candlelight_fw.html
* ⚠️ Bug sprzętowy MKS PRO przy szybkim resecie: https://github.com/makerbase-mks/CANable-MKS/issues/6
  (workaround: odczekaj ~2 s po odłączeniu zasilania; albo przeprogramowanie
  option bytes przez SWD — szczegóły w repo SebKuzminsky).

## Terminacja 120 Ω

Płytka ma zworkę/opcję terminacji 120 Ω:
* **W aucie: OFF** — magistrala jest już terminowana przez moduły.
* Łączówka „na stole" z jednym węzłem: można zostawić OFF (ruch i tak nie
  powstanie); przy testach z drugim węzłem — włącz na dwóch końcach.

## Windows — szybkie sprawdzenie urządzenia

```powershell
py sniff.py --list-ports
py selftest.py --port COM7
```

## Linux (dla odniesienia)

* slcan: `slcand -o -c -s6 /dev/ttyACM0 can0 && ip link set can0 up && candump can0`
  (s6 = 500k; więcej: can-utils, https://github.com/linux-can/can-utils)
* candlelight: plug&play (`can0` pojawia się samo).
