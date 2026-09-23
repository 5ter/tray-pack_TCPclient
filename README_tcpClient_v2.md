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

## Full service: no printing yet

After the read-only test passes, start the full event detector without sending
events to the existing result server:

```powershell
$env:FORWARD_RESULTS = 'false'
python .\tcpClient_v2.py
```

After a new PLC latch changes ON, expected output is:

```text
NEW OK event id=... from M7
Event ready for future PC pipeline: OK
```

The full service creates `tray_events.sqlite3` in this folder. That is a local
durable event queue. It does not print a label or alter a Box ID at this stage.

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
