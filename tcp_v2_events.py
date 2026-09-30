"""Small value object for one PLC inspection result."""

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid


@dataclass(frozen=True)
class InspectionEvent:
    """One new M7 or M8 edge detected by the PC."""

    event_id: str
    machine_id: str
    status: str
    occurred_at_utc: str

    @classmethod
    def create(cls, machine_id: str, status: str) -> "InspectionEvent":
        return cls(
            event_id=str(uuid.uuid4()),
            machine_id=machine_id,
            status=status,
            occurred_at_utc=datetime.now(timezone.utc).isoformat(),
        )
