"""Summarize fleet events and render a Slack-ready shift report."""
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class VehicleSummary:
    vehicle: str
    errors: Counter = field(default_factory=Counter)      # display category -> count
    recoveries: Counter = field(default_factory=Counter)  # recovery text -> count
    trips: Optional[int] = None
    km: Optional[float] = None

    @property
    def total(self) -> int:
        return sum(self.errors.values())


def _ranked(counter: Counter):
    """Most common first; ties broken alphabetically so output is deterministic."""
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0].lower()))


def summarize(events, trips=None, vehicles=None) -> Dict[str, VehicleSummary]:
    """vehicles: names to list even when they had no events (clean vehicles)."""
    summaries: Dict[str, VehicleSummary] = {}
    for name in vehicles or []:
        summaries.setdefault(name, VehicleSummary(name))
    display: Dict[str, str] = {}  # casefolded category -> first-seen spelling

    for ev in events:
        s = summaries.setdefault(ev.vehicle, VehicleSummary(ev.vehicle))
        name = display.setdefault(ev.category.casefold(), ev.category)
        s.errors[name] += 1
        s.recoveries[ev.recovery] += 1

    for vehicle, (n, km) in (trips or {}).items():
        s = summaries.setdefault(vehicle, VehicleSummary(vehicle))
        s.trips, s.km = n, km
    return summaries


def find_repeats(summaries, threshold=2):
    out = []
    for v in sorted(summaries):
        for cat, n in _ranked(summaries[v].errors):
            if n >= threshold:
                out.append((v, cat, n))
    return out


def _fmt_counts(counter: Counter) -> str:
    return ", ".join(f"{k} ×{n}" for k, n in _ranked(counter))


def render_slack(summaries, label="Shift", events=None, repeat_threshold=2, skipped=0,
                 unreachable=None) -> str:
    lines = [f"*{label} Report*"]

    stamps = [e.timestamp for e in (events or []) if e.timestamp]
    if stamps:
        lo, hi = min(stamps), max(stamps)
        lines.append(f"_{lo:%d %b %H:%M} → {hi:%d %b %H:%M}_")

    lines += ["", "*Vehicles*"]
    if not summaries:
        lines.append("• No data")
    for v in sorted(summaries):
        s = summaries[v]
        head = f"• *{v}*"
        if s.trips is not None:
            head += f": {s.trips} trips / {s.km:.2f} km"
        lines.append(head)
        if s.total == 0:
            lines.append("   ◦ No errors")
        else:
            lines.append(f"   ◦ {s.total} errors: {_fmt_counts(s.errors)}")
            lines.append(f"   ◦ Recovery: {_fmt_counts(s.recoveries)}")

    repeats = find_repeats(summaries, repeat_threshold)
    if repeats:
        lines += ["", "*Repeat issues*"]
        for v, cat, n in repeats:
            lines.append(f"• ⚠ {v}: {cat} occurred {n}×")

    if unreachable:
        lines += ["", "*Unreachable*"]
        for v in sorted(unreachable):
            lines.append(f"• ⚠ {v}: {unreachable[v]}, not included in this report")

    total = sum(s.total for s in summaries.values())
    overall = Counter()
    for s in summaries.values():
        overall.update(s.errors)
    lines += ["", "*Overall*", f"• {total} errors across {len(summaries)} vehicle(s)"]
    if overall:
        top, n = _ranked(overall)[0]
        lines.append(f"• Most common: {top} ({n})")
    if skipped:
        lines.append(f"• _{skipped} malformed row(s) skipped_")
    return "\n".join(lines)
