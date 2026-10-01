"""CSV loading for events and trips. Tolerant of messy real-world logs."""
import csv
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple


@dataclass
class Event:
    vehicle: str
    category: str
    recovery: str
    timestamp: Optional[datetime]


def _norm(text) -> str:
    return " ".join((text or "").split())


def _parse_ts(text) -> Optional[datetime]:
    text = _norm(text)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _columns(reader, path, required):
    cols = {c.strip().lower(): c for c in (reader.fieldnames or [])}
    for name in required:
        if name not in cols:
            raise ValueError(f"{path}: missing required column '{name}'")
    return cols


def read_events(path) -> Tuple[List[Event], int]:
    """Read events.csv with columns: vehicle, category [, recovery, timestamp].
    Returns (events, skipped_row_count)."""
    events, skipped = [], 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = _columns(reader, path, ("vehicle", "category"))
        for row in reader:
            vehicle = _norm(row.get(cols["vehicle"]))
            category = _norm(row.get(cols["category"]))
            if not vehicle or not category:
                skipped += 1
                continue
            recovery = _norm(row.get(cols["recovery"])) if "recovery" in cols else ""
            ts = _parse_ts(row.get(cols["timestamp"])) if "timestamp" in cols else None
            events.append(Event(vehicle, category, recovery or "unrecorded", ts))
    return events, skipped


def read_trips(path) -> Tuple[Dict[str, Tuple[int, float]], int]:
    """Read trips.csv with columns: vehicle, trips, km. Rows for the same
    vehicle are summed. Returns ({vehicle: (trips, km)}, skipped_row_count)."""
    totals, skipped = {}, 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = _columns(reader, path, ("vehicle", "trips", "km"))
        for row in reader:
            vehicle = _norm(row.get(cols["vehicle"]))
            try:
                trips = int(float(row.get(cols["trips"]) or ""))
                km = float(row.get(cols["km"]) or "")
            except ValueError:
                skipped += 1
                continue
            if not vehicle:
                skipped += 1
                continue
            t, k = totals.get(vehicle, (0, 0.0))
            totals[vehicle] = (t + trips, k + km)
    return totals, skipped
