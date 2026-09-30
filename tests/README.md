# Tests

Run the offline unit tests from the client repository root:

```powershell
python -B -m unittest discover -s tests -t .
```

`manual/` contains opt-in diagnostics rather than unit tests:

- `python -m tests.manual.read_plc_latches` reads the real PLC M7/M8 signals. It is read-only, but run it only when you intend to connect to the machine.
- `python -m tests.manual.check_pymodbus_install` checks PyModbus imports and does not connect to a device.
