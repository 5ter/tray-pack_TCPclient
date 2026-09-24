"""Python implementation of the original SATO SBPL label transmission."""

from __future__ import annotations

from dataclasses import dataclass
import socket

from tcp_v2_config import Settings


class PrinterError(RuntimeError):
    """The PC could not open/write the raw TCP printer socket."""


@dataclass(frozen=True)
class LabelData:
    customer_part_number: str
    date_code: str
    quantity: int
    delivery_date: str
    box_id: str
    spec: str
    remarks: str


class SatoPrinter:
    """Build and send the existing SBPL layout to the configured SATO printer."""

    STX = "\x02"
    ETX = "\x03"
    ESC = "\x1b"

    def __init__(self, settings: Settings) -> None:
        self._host = settings.printer_ip
        self._port = settings.printer_port
        self._timeout = settings.printer_timeout_seconds

    def _field(self, label: str, value: str, vertical: str, chinese_hex: str = "") -> str:
        esc = self.ESC
        chinese = f"{esc}L0202{esc}K1K{chinese_hex}" if chinese_hex else ""
        return (
            f"{esc}H00020{esc}V{vertical}{esc}P02{esc}RDB@0,040,040,{label}{chinese}"
            f"{esc}H00450{esc}V{vertical}{esc}P02{esc}RDB@0,040,040,: {value}"
        )

    def build_sbpl(self, label: LabelData) -> str:
        """Return the original-format label command, using the supplied job data."""
        esc = self.ESC
        padded_quantity = str(label.quantity).zfill(6)
        barcode_data = f"{label.customer_part_number}{padded_quantity}{label.box_id}"
        qr_data = ";".join(
            [
                label.customer_part_number,
                label.date_code,
                "AAZ-AAX",
                label.date_code,
                str(label.quantity),
                label.spec,
                label.box_id,
                "Made in Malaysia",
                label.remarks,
            ]
        )

        fields = "".join(
            [
                self._field("Company ", "ACTMAX", "00150", "28B3A7C9CCC3FBB3C629"),
                self._field("Quanta P/N ", label.customer_part_number, "00210", "28C1CFBAC529"),
                self._field("Date Code ", label.date_code, "00270", "28D6DCC6DAC2EB29"),
                self._field("Vendor Code ", "AAZ-AAX", "00330", "28B3A7C9CCB4FAC2EB29"),
                self._field("Quantity ", str(label.quantity), "00390", "28CAFDC1BF29"),
                self._field("Delivery Date ", label.delivery_date, "00450", "28BDBBBBF5C8D5C6DA29"),
                self._field("Box ID ", label.box_id, "00510", "28CFE4BAC529"),
                self._field("Lot Code ", label.date_code, "00570", "28C5FAB4CEBAC529"),
                self._field("Spec (Desp) ", label.spec, "00630"),
                self._field("Mfg. Site ", "Made in Malaysia", "00690", "28D6C6D4ECB5D829"),
                self._field("Remarks", label.remarks, "00750"),
            ]
        )

        printer_setup = (
            f"{self.STX}{esc}A{esc}A3V+00000H+00000{esc}CS6{esc}#F10A"
            f"{esc}A1V00900H01200{esc}Z{self.ETX}"
        )
        body = (
            f"{self.STX}{esc}A{esc}PS{esc}WKLabel"
            f"{esc}KS3{esc}KC5{esc}H00200{esc}V00050{esc}L0101{esc}P1"
            f"{esc}X24,1Quanta Delivery Label {esc}L0202{esc}K2KB9E3B4EFBDBBBBF5B1EAC7A9"
            f"{fields}"
            f"{esc}H00160{esc}V00810{esc}BG02050>H{barcode_data}"
            f"{esc}V00150{esc}H00800{esc}2D30,H,06,1,0{esc}DN00{len(qr_data)},{qr_data}"
            f"{esc}Q1{esc}Z{self.ETX}"
        )
        return printer_setup + body

    def print_label(self, label: LabelData) -> None:
        try:
            with socket.create_connection((self._host, self._port), timeout=self._timeout) as printer_socket:
                printer_socket.sendall(self.build_sbpl(label).encode("ascii", errors="replace"))
        except OSError as error:
            raise PrinterError(f"Cannot send label to SATO printer {self._host}:{self._port}: {error}") from error
