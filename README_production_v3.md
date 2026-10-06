# Tray inspection production flow

## Operator flow

1. The operator opens `Production_Select.html`, enters their name or ID, searches the registered part-number list, and selects a part number.
2. Starting production creates a new run ID and saves the self-reported operator name/ID with the active run. Starting again, even with the same part, starts a separate run with fresh counts.
3. The PC polls PLC M7 (OK) and M8 (NG). Each OFF-to-ON transition creates an event with a unique ID and is associated with the selected part and run ID.
4. The PC commits the result to its local SQLite outbox (`result_outbox.sqlite3`) before returning to PLC polling.
5. Every 10 seconds, the PC sends up to 100 queued results in one request to `http://192.168.40.29:3168/inspection-results/batch`.
6. The Node API stores the part, result, UTC timestamp, machine ID, operator name/ID, run ID, and event ID in MySQL. It acknowledges the event IDs; only acknowledged rows are removed from the PC outbox.
7. `Production_Run.html` refreshes OK, NG, and total counts for the current run from the server.

The active part, operator name/ID, and run ID are stored in `active_run.json` on the PC and survive a client-service restart. The operator value is self-reported and is not authenticated; it identifies who was entered for that run. There is no Stop/End control: selecting a part and starting again replaces the active run. A PLC event received before a run is selected is logged and ignored.

## Result delivery behavior

The local outbox is durable: each result is committed to SQLite synchronously before it is considered queued, and the network sender runs separately from PLC polling. If the API is unavailable or a request fails, the result stays on disk and is retried on the next 10-second cycle. Pending results also survive a PC service restart and application deployment. The workflow preserves `*.sqlite3` files, including `result_outbox.sqlite3`.

The PC creates a unique `eventId` when it detects each PLC result. MySQL enforces uniqueness, so if the API stored a result but its acknowledgement was lost, resending the same event ID does not add a duplicate count. The client removes a queued result only after receiving its event ID in the API's `acceptedEventIds` response. Batch requests contain at most 100 events by default; the interval and batch size can be changed with `RESULT_BATCH_INTERVAL_SECONDS` and `RESULT_BATCH_SIZE` (batch size must stay at or below 100).

The outbox uses Python's built-in `sqlite3` module, so no additional Python package is required.

The running page shows counts confirmed by the server. While the API is offline, these counts may lag behind the local queue; after reconnection and successful delivery, the page's next refresh includes the stored results. Check `tcp_client_v2.log` for messages about local queueing, retry failures, and server acknowledgements. If the PC itself cannot write to its SQLite outbox (for example, disk or permissions failure), the result cannot be durably queued and a critical error is logged.

This queue protects results after the PC has detected an M7/M8 edge and committed it locally. It cannot recover an edge that occurs while the PC service is stopped or that the polling loop never observes, and a local disk failure can prevent the initial save. Covering those cases would require a PLC-held-until-ack signal or a PLC event counter/history, which this version does not use.

## PC API and UI

The Python service still listens on `127.0.0.1:3000` by default and serves the static pages from this project folder.

- `GET /api/parts` loads the registered part-number dropdown.
- `POST /api/run/start` validates a part number and creates the new local run context.
- `GET /api/run-summary` reads counts for the active run from the DB API.
- `GET /api/plc-status` exposes whether the latest PLC M7/M8 poll succeeded.

`/run-summary` is a read-only query: the Node API counts the OK/NG rows already stored for the active run in MySQL. The running page refreshes those counts every 3 seconds so they update without a manual refresh. Results are uploaded in batches every 10 seconds, so the count can naturally lag the PLC by up to roughly one upload interval plus the next page refresh. The polling does not create or submit inspection results. A separate PLC badge reports whether the client most recently read M7/M8 successfully; it does not infer PLC health from the database/API connection.

The legacy URLs `/Log_In.html`, `/Register.html`, and `/Running.html` are still redirected to the new screens by the Python web server. Registration keeps the existing administrator login and registers only a unique part number.

## Repository layout

- The active Python service modules, `tcpClient_v2.py`, and current UI pages stay in the project root because NSSM and the deployment workflow expect those paths.
- `tests/` contains offline unit tests. `tests/manual/` contains diagnostics that are run only when needed.
- `obsolete/` holds the superseded V2 guide, old entrypoints, and prior UI pages. They are archived, not used by the current service. The Python web server still handles the old page URLs as redirects.
- Local state and runtime files such as `active_run.json`, `result_outbox.sqlite3`, and logs remain outside those folders so deployment does not disturb them.

## Tests

From the project root, run the offline unit tests with:

```powershell
python -B -m unittest discover -s tests -t .
```

Manual diagnostics are separate from unit-test discovery. `python -m tests.manual.read_plc_latches` reads the live PLC M7/M8 latches without writing; run it only when you intentionally want to check the machine signal. `python -m tests.manual.check_pymodbus_install` checks the installed PyModbus imports and does not connect to a device.

## MySQL API and schema

The Node API is in the sibling `tray-pack_server` repository. The new endpoints are:

- `GET /parts`
- `POST /register-part` with `{ "partNumber": "..." }`
- `POST /inspection-results/batch` with a JSON body such as:

  ```json
  {
    "events": [{
      "eventId": "6f1d2dc6-581e-41a6-91b4-9edaf931ef6b",
      "partNumber": "PART-123",
      "status": "OK",
      "timestampUtc": "2026-09-30T01:02:03.000Z",
      "machineId": "TRAY-PACK-01",
      "operatorName": "Operator A",
      "runId": "7c90ad28-8fba-4dc4-97f7-51c98029efad"
    }]
  }
  ```

  A successful response contains `{ "acceptedEventIds": [...] }`.
- `POST /inspection-results` remains available for one-off compatibility and can accept the same event fields (including an optional `eventId`)
- `GET /run-summary?runId=...&partNumber=...`
- Existing `POST /login` remains in use.

Apply `tray-pack_server/migrations/001_production_tables.sql`, `002_inspection_event_ids.sql`, and `003_inspection_operator.sql` to the existing `tray` MySQL database before using the new screens with the queued sender. Run them once in order. If 001 and 002 have already been applied, back up the database and apply only 003. Migration 001 creates `registered_parts` and `inspection_results`, then copies distinct existing part numbers from `label_print_data` into the new part list. Migration 002 adds the unique event ID used for retry deduplication. Migration 003 adds `operator_name`; pre-existing results receive `UNKNOWN`. Existing `label_print_data` and `user_log_in` rows and legacy API routes are not deleted. These migration files do not themselves connect to or modify the live database; run them manually on the database server after taking a backup.

The DB API must be deployed and restarted separately from the PC NSSM service. The new Node routes were added alongside the old printing-era routes to keep the existing server available during transition; the new client does not call the old routes. The NSSM GitHub Action in `.github/workflows/deploy-nssm.yml` only deploys the PC client.

Recommended rollout order: back up the MySQL `tray` database, apply the SQL migration on the DB server, deploy/restart the Node API from `tray-pack_server`, then push the PC client changes to `main` so its NSSM deployment runs.

## Starting the new production tables fresh

This permanently deletes inspection history and registered parts from the two new tables. Stop production and stop the PC NSSM service first. Let the local outbox deliver its pending events before resetting the server tables; otherwise queued events can be rejected after their part numbers are deleted. You can check the default local outbox on the PC with:

```powershell
python -c "import sqlite3; c=sqlite3.connect('result_outbox.sqlite3'); print(c.execute('SELECT COUNT(*) FROM pending_results').fetchone()[0]); c.close()"
```

If `RESULT_OUTBOX_PATH` is configured, run that command against the configured SQLite file instead. Make a database backup, then in MySQL Workbench or the MySQL command line select the `tray` database and run:

```sql
START TRANSACTION;
DELETE FROM inspection_results;
DELETE FROM registered_parts;
COMMIT;
```

Delete child rows first because `inspection_results` references `registered_parts`. Register the required part numbers again before starting production. This does not clear or modify the legacy `label_print_data` or `user_log_in` tables. Do not clear the local outbox as part of a normal reset; if it is non-empty, allow delivery to finish before running the SQL above.

## PLC behavior

The client remains a Modbus TCP client. It reads the final result latches M7 (OK) and M8 (NG), plus D1 for the camera mode. It does not read camera raw inputs or write to the PLC. Results are detected once on OFF-to-ON transitions; an already-high latch at PC startup is treated as the initial state and not counted.

For Xinje XD/XL PLCs, the Modbus map documents D0 at holding-register address 0, so D1 is address 1. `CAMERA_MODE_REGISTER_ADDRESS` can override that address if the installed PLC model uses another map. The PC reads the register; the PLC/HMI remains the source of the mode.

## Hikrobot camera mode TCP service

The PC also listens for the Hikrobot cameras as TCP clients. Defaults are `CAMERA_TCP_HOST=0.0.0.0` and `CAMERA_TCP_PORT=5001`; the cameras connect to the PC's machine-network IP and this port. Each connection receives the current D1 value, and connected cameras receive another line when D1 changes. A camera may also send `GET_MODE` followed by a newline to request the latest value again.

The line protocol is ASCII with CRLF termination: `MODE=0\r\n`, `MODE=1\r\n`, etc. If D1 cannot currently be read, the server sends `MODE=UNKNOWN\r\n` instead of guessing. The server sends the raw PLC word, not a translated label; configure the camera's VisionMaster/SCVision flow to parse the line and map the D1 values to its camera logic. Both cameras may connect at the same time. The listener does not write to the PLC.

Configure each camera's communication tool as a TCP client pointed at the PC IP and port 5001, with a receive parser that uses CRLF as the message boundary. Add a Windows Firewall inbound TCP rule for this port limited to the camera IPs/subnet. The model and VisionMaster/SCVision version can change the available receive settings, so verify the exact camera configuration before production use.

Settings can be overridden through the NSSM service environment:

```text
CAMERA_MODE_REGISTER_ADDRESS=1
CAMERA_TCP_HOST=0.0.0.0
CAMERA_TCP_PORT=5001
```
