"""Rule-driven log parser: turns raw robot log lines into Events.

Rules live in a JSON file so the log format can be tuned without code changes:
  {"timestamp": {"regex": "^(\\d{4}-\\d{2}-\\d{2} [\\d:]+)", "format": "iso"},
   "rules": [{"pattern": "lidar.*timeout", "category": "LiDAR", "recovery": "power cycle"}]}
First matching rule wins. category/recovery may use \\1-style group references.
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from .loader import Event

DEFAULT_TS = {"regex": r"^\[?(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})", "format": "iso"}


@dataclass
class Rules:
    ts_regex: "re.Pattern"
    ts_format: str
    rules: list  # (compiled pattern, category, recovery)


def load_rules(path) -> Rules:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw = data.get("rules")
    if not raw:
        raise ValueError(f"{path}: 'rules' list is required and must not be empty")
    ts = data.get("timestamp", DEFAULT_TS)
    try:
        compiled = []
        for r in raw:
            compiled.append((re.compile(r["pattern"], re.IGNORECASE), r["category"], r.get("recovery", "")))
        return Rules(re.compile(ts["regex"]), ts.get("format", "iso"), compiled)
    except re.error as e:
        raise ValueError(f"{path}: invalid regex ({e})")
    except KeyError as e:
        raise ValueError(f"{path}: rule missing required key {e}")


def _parse_ts(line, rules: Rules) -> Optional[datetime]:
    m = rules.ts_regex.search(line)
    if not m:
        return None
    text = m.group(1)
    try:
        if rules.ts_format == "iso":
            return datetime.fromisoformat(text)
        return datetime.strptime(text, rules.ts_format)
    except ValueError:
        return None


def parse_log(lines, rules: Rules, vehicle: str) -> List[Event]:
    events = []
    for line in lines:
        for pattern, category, recovery in rules.rules:
            m = pattern.search(line)
            if m:
                events.append(Event(
                    vehicle=vehicle,
                    category=m.expand(category),
                    recovery=m.expand(recovery) if recovery else "unrecorded",
                    timestamp=_parse_ts(line, rules),
                ))
                break
    return events
