# 09 — Sterowanie agentowe (CLI + `ctl`)

Program jest w pełni sterowalny z linii poleceń — dla agentów i skryptów.
Są dwie ścieżki (można mieszać):

## 1. Bez GUI — `py -m canstudio <komenda>` z `--json` / `--jsonl`

Komendy mają tryb maszynowy: `--json` (jeden obiekt na końcu) lub `--jsonl`
(strumień: jedna linia na ramkę/zdarzenie). W tym trybie „ludzki” tekst leci
na **stderr**, a **stdout** zostaje czysty dla parsera.

```powershell
py -m canstudio sniff --channel COM7 --duration 10 --json          # podsumowanie
py -m canstudio sniff --channel COM7 --jsonl --duration 10 > ramki.jsonl
py -m canstudio scan   --channel COM7 --json
py -m canstudio discover logs\x.log --json
py -m canstudio checksum logs\x.log --json
py -m canstudio correlate logs\marks.log --json
py -m canstudio stats  logs\x.log --json
py -m canstudio autodbc logs\x.log --json
py -m canstudio uds scan --ids 600-6FF --json
py -m canstudio uds read --txid 6F1 F190 F18C --json
py -m canstudio uds dtc  --txid 6F1 --json
py -m canstudio send   --channel COM7 --id 0x123 --data DEADBEEF --json
py -m canstudio replay logs\x.log --set "0x130:3=0x2A" --counter 0x130:1 --json
py -m canstudio ports --json
```

Kody wyjścia: 0 = OK, ≠0 = błąd.

## 2. Z GUI — `py -m canstudio ctl …` (klient działającego Studia)

`ctl` steruje uruchomionym serwerem (`py -m canstudio gui`) po REST + WebSocket.
Przydatne, gdy agent ma współdzielić jedną magistralę z człowiekiem albo
odpytywać stan sesji. Wyjście: **zawsze JSON** (kompakt; `--pretty` = wcięcia).

```powershell
py -m canstudio ctl status
py -m canstudio ctl connect --interface virtual --demo
py -m canstudio ctl frames --seconds 5 --summary       # JSONL z WebSocket
py -m canstudio ctl uds-scan --ids 600-6FF
py -m canstudio ctl uds-read --txid 6F1 --dids F190,F18C
py -m canstudio ctl log-stats --file demo_b.log
py -m canstudio ctl replay-start --file x.log --rate 2 --rules '{"set":[{"id":"0x130","byte":3,"value":"231"}]}'
py -m canstudio ctl call /api/status                   # dowolny endpoint REST
py -m canstudio ctl call /api/send --method POST --body '{"id":"0x123","data":"DEADBEEF"}'
```

Pełna lista komend: `py -m canstudio ctl -h`.
Domyślny adres: `http://127.0.0.1:8077` (`--url` zmienia; przy auto-porcie:
np. `ctl --url http://127.0.0.1:8080 status`).
Kody wyjścia: 0 = OK, 2 = błąd/serwer niedostępny.

## 3. Serwer MCP (natywna integracja)

Uruchomienie: `py -m canstudio mcp` (wymaga: `py -m pip install mcp`).

**15 narzędzi**:
`can_ports`, `can_sniff`, `can_scan`, `can_log_stats`, `can_discover`,
`can_checksum`, `can_correlate`, `can_autodbc`, `can_uds`, `can_send`,
`can_replay`, `gui_status`, `gui_connect`, `gui_frames`, `gui_call`.

Konfiguracja klienta (mcporter / Claude Desktop itp. — JSON):

```json
{
  "mcpServers": {
    "mirican-studio": {
      "command": "py",
      "args": ["-m", "canstudio", "mcp"],
      "env": {"PYTHONPATH": "<ścieżka do can-toolkit>"}
    }
  }
}
```

W tym komputerze wpis jest **już dodany** (mcporter): `mcporter list` → mirican-studio
(15 tools); `mcporter call mirican-studio.can_ports`.

GUI: panel **AGENT (MCP)** u dołu ekranu (dock, trzeci panel obok klasyfikacji i sygnałów) —
status + „📋 kopiuj konfigurację” + ⟳ odświeżanie.

## Wskazówki dla agentów

- Parsuj **stdout**; komunikaty i progres są na stderr (tryb `--json*`).
- `sniff --jsonl` i `watch --jsonl` nadają się do czytania strumieniowego.
- `ctl frames` = najprostszy sposób pobrania żywych ramek z sesji GUI (JSONL).
- `ctl log-trim`/`replay-start` domykają pętlę „nagraj → przeanalizuj → odtwórz
  z modyfikacją” bez dotykania GUI.
- Bezpieczeństwo: operacje modyfikujące (send, uds write/reset, --clear,
  replay na realnej magistrali) — tylko postój/ławka; `ctl` przekazuje
  wymagane potwierdzenia (`confirm`) do serwera.
