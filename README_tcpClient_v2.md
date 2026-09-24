# tcpClient_v2: simple file map and first PLC test

## Start here: a read-only PLC test

Use `test_plc_latches.py` before starting the full service. It is read-only:
it only reads PLC `M7` (OK) and `M8` (NG). It does not write a PLC coil or
register, print, create Box IDs, create a database, or send to the result
server.

From PowerShell in this folder:

```powershell
python .\test_plc_latches.py
```

Expected first output when the PLC connection and Modbus addresses are correct:

```text
Read-only test: PLC 192.168.6.6:502
Configured mapping: Modbus coil 7 = M7 / OK
Configured mapping: Modbus coil 8 = M8 / NG
Connected. Current state: M7 / OK = False; M8 / NG = False
```

Run one controlled OK and one controlled NG tray. The display should show
changes similar to:

```text
M7 / OK changed: False -> True
M7 / OK changed: True -> False
M8 / NG changed: False -> True
M8 / NG changed: True -> False
```

If it repeatedly reports `PLC connection failed`, verify PLC IP, port 502,
network cabling, Modbus TCP-server settings, PC firewall, and Modbus mapping.
The original `main.py` already uses coil addresses 7 and 8; these defaults
preserve that convention.

## What “OFF -> ON” means

The client reads the PLC every 0.2 second by default.

```text
Previous poll: M7 = OFF / False
Current poll:  M7 = ON  / True
                           ^
                           One new OK tray result
```

`M7` can stay ON for several seconds because it is a PLC latch. The client
records one event only at the first OFF -> ON transition and ignores later
polls while it remains ON. This is what prevents one accepted tray causing
repeated counting or label printing in the future.

The same rule is used independently for `M8` and an NG event.

At PC startup the full client reads the initial state but does not count it.
That avoids treating an old result still latched in the PLC as a new tray.

## Source-file responsibilities

| File | Purpose |
|---|---|
| `test_plc_latches.py` | Read-only M7/M8 test. Run this first. |
| `tcpClient_v2.py` | Small launcher for the full service. |
| `tcp_v2_config.py` | PLC addresses, poll interval, machine ID, and server settings. |
| `tcp_v2_plc.py` | The only code that calls Modbus and reads M7/M8. |
| `tcp_v2_service.py` | Flow: latch change -> inspection event -> local queue -> optional forwarding. |
| `tcp_v2_events.py` | Defines an event and keeps it in a local SQLite queue. |
| `tcp_v2_sender.py` | Sends queued JSON to existing `server.py`, if enabled. |
| `tcp_v2_db.py` | Calls the existing `/get-project-data` and `/update-box-id` database API. |
| `tcp_v2_job.py` | Holds the active PC job and generates Box IDs after final OK events. |
| `tcp_v2_printer.py` | Python conversion of the existing SATO SBPL label transmission. |
| `tcp_v2_web.py` | Hosts the legacy HTML pages and Python API at `localhost:3000`. |

```text
PLC M7/M8
    |
    v
tcp_v2_plc.py
    |
    v
tcp_v2_service.py  -- detects OFF -> ON once
    |
    +--> tcp_v2_events.py  -- stores event safely on this PC
    |
    +--> tcp_v2_sender.py  -- optional forwarding to port 3333
```

## Full service: old DB API, safe printing default

After the read-only test passes, start the migrated PC service:

```powershell
python .\tcpClient_v2.py
```

It starts two PC functions:

```text
http://127.0.0.1:3000/Log_In.html  -> operator job page and Python API
PLC Modbus TCP poller                -> reads final M7/M8 latches
```

On the job page, enter the same Spec and delivery date used by the old system.
Python calls the unchanged database endpoint:

```text
POST http://192.168.40.29:3168/get-project-data
```

The active job is saved locally in `active_job.json`, so the PC knows the
product, last Box ID, and current Box-ID counter after a service restart.

`ENABLE_PRINTING` is **false by default**. Thus, an M7 event produces this
safe dry-run result:

```text
NEW OK event id=... from M7
DRY RUN: M7/OK would print Box_ID=... for spec=...
```

With printing disabled, no label is sent and the database Box ID is not changed.
M8/NG events never send a shipping label.

Only after the job setup and dry-run Box ID are verified should printing be
explicitly enabled for a controlled label test:

```powershell
$env:ENABLE_PRINTING = 'true'
python .\tcpClient_v2.py
```

With printing enabled, an M7 event runs this compatibility sequence:

```text
M7 changes OFF -> ON
  -> generate next Box ID on the PC
  -> send the converted SBPL label to 192.168.6.20:9100
  -> POST /update-box-id to 192.168.40.29:3168
  -> save the new current Box ID in active_job.json
```

Before a physical label is sent, its candidate Box ID is saved as `pending` in
`active_job.json`. If either the printer write or database update fails, the
PC blocks later automatic labels instead of risking reuse of an ID that may
already have been printed. Resolve that error before resetting or starting a
new job.

The legacy `Running.html` change-product button now resets the **PC job** only.
No reset or tray-count command is written to the PLC. Its old override button
returns a clear “not used in version 2” message because M7/M8 are final tray
events and this version has no PLC tray counter to override.

`tray_events.sqlite3` remains a local durable event queue. The former
port-3333 result forwarding is disabled by default; set `FORWARD_RESULTS=true`
only if that old logging receiver is intentionally in use.

## Packages

Python's standard library supplies logging, SQLite, sockets, JSON, time, and
file handling. The only external package is `pymodbus`.

It is already installed in this development environment (`pymodbus 3.15.0`).
On another PC, install it once with:

```powershell
python -m pip install -r .\requirements_tcpClient_v2.txt
```

## Settings without editing code

PowerShell example for a different PLC address:

```powershell
$env:PLC_IP = '192.168.6.6'
$env:OK_COIL_ADDRESS = '7'
$env:NG_COIL_ADDRESS = '8'
python .\test_plc_latches.py
```

Do not change coil numbers unless the read-only test proves the mapping wrong.
Modbus address bases can differ between PLC configurations.
