"""Print a clearly marked test label from the saved active job.

This utility is intentionally independent from tcpClient_v2.py. It does not:
* connect to the PLC;
* change active_job.json;
* increment the real Box-ID counter; or
* call the database /update-box-id endpoint.

Use --send only for a controlled physical printer/layout test. The label uses a
non-production Box ID beginning with TEST and remarks stating DO NOT SHIP.
"""

from __future__ import annotations

import argparse
import sys

from tcp_v2_config import Settings
from tcp_v2_job import JobError, JobStateStore
from tcp_v2_printer import LabelData, PrinterError, SatoPrinter


def test_box_id(real_box_id: str) -> str:
    """Keep the expected shape while making the printed test ID non-production."""
    if len(real_box_id) >= 4:
        candidate = f"TEST{real_box_id[4:]}"
        if candidate != real_box_id:
            return candidate
        return f"TST0{real_box_id[4:]}"
    return f"TEST-{real_box_id}"


def load_test_label(settings: Settings) -> LabelData:
    job, pending_box_id, _ = JobStateStore(settings.job_state_path).load()
    if job is None:
        raise JobError(f"No active job exists in {settings.job_state_path}")
    if pending_box_id is not None:
        raise JobError(
            f"Box_ID={pending_box_id} is pending from a real job. Resolve it before a test print."
        )

    remarks = f"{job.remarks} | TEST PRINT - DO NOT SHIP".strip(" |")
    return LabelData(
        customer_part_number=job.customer_part_number,
        date_code=job.date_code,
        quantity=job.quantity,
        delivery_date=job.delivery_date,
        box_id=test_box_id(job.box_id),
        spec=job.spec,
        remarks=remarks,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview or send a non-production test label.")
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send the TEST label to the configured SATO printer.",
    )
    arguments = parser.parse_args()
    settings = Settings()

    try:
        label = load_test_label(settings)
    except JobError as error:
        print(f"Cannot prepare test label: {error}")
        return 1

    print("Test label preview")
    print(f"  Printer: {settings.printer_ip}:{settings.printer_port}")
    print(f"  Spec:    {label.spec}")
    print(f"  P/N:     {label.customer_part_number}")
    print(f"  Box ID:  {label.box_id}")
    print(f"  Remarks: {label.remarks}")
    print("  Database and active-job state will not be changed.")

    if not arguments.send:
        print("Preview only. Re-run with --send to issue this TEST label.")
        return 0

    try:
        SatoPrinter(settings).print_label(label)
    except PrinterError as error:
        print(f"Test print failed: {error}")
        return 1

    print("TEST label sent to printer. Do not use it for shipment.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
