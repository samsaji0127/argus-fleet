"""Deterministic synthetic fleet data for demos and examples."""
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

from .loader import Event

CATEGORIES = ["Safety PLC", "Control Module", "Device Monitor", "Peripherals",
              "Camera", "LiDAR", "CAN Drivers", "Drivable Region"]
RECOVERIES = ["fleet mode switch", "manual switch", "power cycle", "reset pose"]
VEHICLES = ["VEH-A", "VEH-B"]


def demo_events(n=27, seed=7):
    rng = random.Random(seed)
    t = datetime(2026, 1, 1, 22, 0)
    events = []
    for _ in range(n):
        t += timedelta(minutes=rng.randint(5, 40))
        events.append(Event(rng.choice(VEHICLES), rng.choice(CATEGORIES),
                            rng.choice(RECOVERIES), t))
    return events


def demo_trips():
    return {"VEH-A": (43, 6.81), "VEH-B": (24, 3.32)}


def write_examples(directory):
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "events.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "vehicle", "category", "recovery"])
        for e in demo_events():
            w.writerow([e.timestamp.isoformat(sep=" "), e.vehicle, e.category, e.recovery])
    with open(d / "trips.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["vehicle", "trips", "km"])
        for v, (n, km) in demo_trips().items():
            w.writerow([v, n, km])
