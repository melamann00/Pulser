import csv
import os
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

def _stable_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.getenv("APPDATA") or str(Path.home())
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.getenv("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    data_dir = Path(base) / "HealthTracker"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

def _migrate_legacy_csv(new_path: Path) -> None:
    if new_path.exists():
        return
    legacy_path = Path(os.path.dirname(os.path.abspath(__file__))) / "health_data.csv"
    if legacy_path.exists() and legacy_path.resolve() != new_path.resolve():
        try:
            shutil.copy2(legacy_path, new_path)
        except OSError:
            pass

FIELDNAMES = ["id", "timestamp", "systolic", "diastolic", "pulse"]
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"

def _migrate_schema(path: Path) -> None:
    if not path.exists():
        return
    try:
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None or set(reader.fieldnames) == set(FIELDNAMES):
                return  # empty, or already on the current schema
            rows = list(reader)
    except OSError:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "id": row.get("id") or uuid.uuid4().hex,
                "timestamp": row.get("timestamp", ""),
                "systolic": row.get("systolic", ""),
                "diastolic": row.get("diastolic", ""),
                "pulse": row.get("pulse", ""),
            })

DATA_FILE = str(_stable_data_dir() / "health_data.csv")
_migrate_legacy_csv(Path(DATA_FILE))
_migrate_schema(Path(DATA_FILE))

def _parse_optional_int(value) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

@dataclass
class Reading:
    timestamp: datetime
    systolic: Optional[int]
    diastolic: Optional[int]
    pulse: int
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    def to_row(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.strftime(TIMESTAMP_FORMAT),
            "systolic": "" if self.systolic is None else self.systolic,
            "diastolic": "" if self.diastolic is None else self.diastolic,
            "pulse": self.pulse,
        }
def ensure_data_file() -> None:
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
def load_readings() -> List[Reading]:
    ensure_data_file()
    readings: List[Reading] = []
    with open(DATA_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                readings.append(
                    Reading(
                        timestamp=datetime.strptime(row["timestamp"], TIMESTAMP_FORMAT),
                        systolic=_parse_optional_int(row.get("systolic")),
                        diastolic=_parse_optional_int(row.get("diastolic")),
                        pulse=int(row["pulse"]),
                        id=row.get("id") or uuid.uuid4().hex,
                    )
                )
            except (ValueError, KeyError, TypeError):
                continue
    readings.sort(key=lambda r: r.timestamp)
    return readings
def add_reading(reading: Reading) -> None:
    ensure_data_file()
    with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(reading.to_row())
def delete_reading(reading_id: str) -> None:
    remaining = [r for r in load_readings() if r.id != reading_id]
    with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for r in remaining:
            writer.writerow(r.to_row())
