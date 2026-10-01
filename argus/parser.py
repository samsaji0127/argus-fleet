"""Rule-driven log parser: turns raw robot log lines into Events.

Rules live in a JSON file so the log format can be tuned without code changes:
  {"timestamp": [{"regex": "^(\\d{4}-\\d{2}-\\d{2} [\\d:]+)", "format": "iso"},
                 {"regex": "^[IWEF](\\d{4} [\\d:.]+)", "format": "%m%d %H:%M:%S.%f"}],
   "merge_gap_s": 60,
   "rules": [{"pattern": "lidar.*timeout", "category": "LiDAR", "recovery": "power cycle"}]}

- First matching rule wins. category/recovery may use \\1-style group references.
- "timestamp" may be one object or a list; the first pattern that matches a line is used.
  A format with no year (like glog's) is read in the current year.
- merge_gap_s (global, or per rule): lines of the same category closer together than
  this many seconds count as ONE incident, so a 500-line burst is not 500 errors.
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from .loader import Event

DEFAULT_TS = {"regex": r"^\[?(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})", "format": "iso"}


@dataclass
class Rules:
    timestamps: list  # (compiled regex, format)
    rules: list       # (compiled pattern, category, recovery, merge_gap_s)


def load_rules(path) -> Rules:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw = data.get("rules")
    if not raw:
        raise ValueError(f"{path}: 'rules' list is required and must not be empty")
    ts_cfg = data.get("timestamp", DEFAULT_TS)
    if isinstance(ts_cfg, dict):
        ts_cfg = [ts_cfg]
    global_gap = float(data.get("merge_gap_s", 0))
    try:
        timestamps = [(re.compile(t["regex"]), t.get("format", "iso")) for t in ts_cfg]
        compiled = []
        for r in raw:
            compiled.append((re.compile(r["pattern"], re.IGNORECASE), r["category"],
                             r.get("recovery", ""), float(r.get("merge_gap_s", global_gap))))
        return Rules(timestamps, compiled)
    except re.error as e:
        raise ValueError(f"{path}: invalid regex ({e})")
    except KeyError as e:
        raise ValueError(f"{path}: missing required key {e}")


def _parse_ts(line, rules: Rules, now: datetime) -> Optional[datetime]:
    for regex, fmt in rules.timestamps:
        m = regex.search(line)
        if not m:
            continue
        text = m.group(1)
        try:
            if fmt == "iso":
                return datetime.fromisoformat(text)
            if "%Y" in fmt or "%y" in fmt:
                return datetime.strptime(text, fmt)
            # No year in the log: assume the current year, or last year if that
            # would land in the future (e.g. a Dec log read in January).
            ts = datetime.strptime(f"{now.year} {text}", f"%Y {fmt}")
            if ts > now + timedelta(days=1):
                ts = datetime.strptime(f"{now.year - 1} {text}", f"%Y {fmt}")
            return ts
        except ValueError:
            return None
    return None


def parse_log(lines, rules: Rules, vehicle: str, now: Optional[datetime] = None) -> List[Event]:
    now = now or datetime.now()
    events, last_seen = [], {}
    for line in lines:
        for pattern, category, recovery, gap in rules.rules:
            m = pattern.search(line)
            if not m:
                continue
            cat = m.expand(category)
            ts = _parse_ts(line, rules, now)
            if gap and ts is not None:
                key = cat.casefold()
                prev = last_seen.get(key)
                last_seen[key] = ts
                if prev is not None and 0 <= (ts - prev).total_seconds() < gap:
                    break  # same incident, still bursting
            events.append(Event(vehicle, cat, m.expand(recovery) if recovery else "unrecorded", ts))
            break
    return events
