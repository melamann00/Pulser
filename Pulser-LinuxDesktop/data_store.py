import csv
import os
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List

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

DATA_FILE = str(_stable_data_dir() / "health_data.csv")
_migrate_legacy_csv(Path(DATA_FILE))

FIELDNAMES = ["id", "timestamp", "heart_rate", "pulse"]
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"

@dataclass
class Reading:
    timestamp: datetime
    heart_rate: int
    pulse: int
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    def to_row(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.strftime(TIMESTAMP_FORMAT),
            "heart_rate": self.heart_rate,
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
                        heart_rate=int(row["heart_rate"]),
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