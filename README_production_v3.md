# Tray inspection production flow

## Operator flow

1. The operator opens `Production_Select.html` and chooses a registered part number.
2. Starting production creates a new run ID. Starting again, even with the same part, starts a separate run with fresh counts.
3. The PC polls PLC M7 (OK) and M8 (NG). Each OFF-to-ON transition creates an event with a unique ID and is associated with the selected part and run ID.
4. The PC commits the result to its local SQLite outbox (`result_outbox.sqlite3`) before returning to PLC polling.
5. Every 10 seconds, the PC sends up to 100 queued results in one request to `http://192.168.40.29:3168/inspection-results/batch`.
6. The Node API stores the part, result, UTC timestamp, machine ID, run ID, and event ID in MySQL. It acknowledges the event IDs; only acknowledged rows are removed from the PC outbox.
7. `Production_Run.html` refreshes OK, NG, and total counts for the current run from the server.

The active part and run ID are stored in `active_run.json` on the PC and survive a client-service restart. There is no Stop/End control: selecting a part and starting again replaces the active run. A PLC event received before a run is selected is logged and ignored.

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

`Log_In.html`, `Register.html`, and `Running.html` redirect to the new screens. Registration keeps the existing administrator login and registers only a unique part number.

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
      "runId": "7c90ad28-8fba-4dc4-97f7-51c98029efad"
    }]
  }
  ```

  A successful response contains `{ "acceptedEventIds": [...] }`.
- `POST /inspection-results` remains available for one-off compatibility and can accept the same event fields (including an optional `eventId`)
- `GET /run-summary?runId=...&partNumber=...`
- Existing `POST /login` remains in use.

Apply `tray-pack_server/migrations/001_production_tables.sql` and then `tray-pack_server/migrations/002_inspection_event_ids.sql` to the existing `tray` MySQL database before using the new screens with the queued sender. Migration 001 creates `registered_parts` and `inspection_results`, then copies distinct existing part numbers from `label_print_data` into the new part list. Migration 002 adds the unique event ID used for retry deduplication. Run each migration once, in order. Existing `label_print_data` and `user_log_in` rows and legacy API routes are not deleted. These migration files do not themselves connect to or modify the live database; run them manually on the database server after taking a backup.

The DB API must be deployed and restarted separately from the PC NSSM service. The new Node routes were added alongside the old printing-era routes to keep the existing server available during transition; the new client does not call the old routes. The NSSM GitHub Action in `.github/workflows/deploy-nssm.yml` only deploys the PC client.

Recommended rollout order: back up the MySQL `tray` database, apply the SQL migration on the DB server, deploy/restart the Node API from `tray-pack_server`, then push the PC client changes to `main` so its NSSM deployment runs.

## PLC behavior

The client remains a Modbus TCP client. It reads only the final result latches: M7 is OK and M8 is NG. It does not read camera raw inputs or write to the PLC. Results are detected once on OFF-to-ON transitions; an already-high latch at PC startup is treated as the initial state and not counted.
