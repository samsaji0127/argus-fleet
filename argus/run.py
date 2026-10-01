"""End-to-end automation: fetch logs -> parse -> filter window -> report."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from .fetch import fetch_log
from .parser import load_rules, parse_log
from .report import render_slack, summarize


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("vehicles"):
        raise ValueError(f"{path}: 'vehicles' list is required")
    for v in cfg["vehicles"]:
        for key in ("name", "log"):
            if key not in v:
                raise ValueError(f"{path}: every vehicle needs '{key}'")
    return cfg


def run_pipeline(config_path, hours=None, label=None, local=False, fetcher=fetch_log, now=None):
    """Returns (report_text, report_path, n_unreachable)."""
    cfg = load_config(config_path)
    base = Path(config_path).resolve().parent
    rules = load_rules(base / cfg.get("rules", "rules.json"))
    data_dir = base / cfg.get("data_dir", "data")
    reports_dir = base / cfg.get("reports_dir", "reports")

    hours = hours if hours is not None else cfg.get("hours")
    label = label or cfg.get("label", "Shift")
    now = now or datetime.now()
    since = now - timedelta(hours=hours) if hours else None

    events, unreachable, fetched, skipped = [], {}, [], 0
    for v in cfg["vehicles"]:
        name = v["name"]
        dest = data_dir / f"{name}.log"
        if local:
            if not dest.exists():
                unreachable[name] = "no local log found"
                continue
        else:
            if "host" not in v:
                raise ValueError(f"vehicle '{name}' needs 'host' (or run with --local)")
            ok, msg = fetcher(v["host"], v["log"], dest, cfg.get("tail_lines"))
            if not ok:
                print(f"argus: {name}: fetch failed: {msg}", file=sys.stderr)
                unreachable[name] = "log could not be fetched"
                continue

        with open(dest, encoding="utf-8", errors="replace") as f:
            found = parse_log(f, rules, name)
        if since:
            kept = [e for e in found if e.timestamp and since <= e.timestamp <= now]
            skipped += sum(1 for e in found if not e.timestamp)
            found = kept
        events.extend(found)
        fetched.append(name)

    summaries = summarize(events, vehicles=fetched)
    text = render_slack(summaries, label=label, events=events,
                        skipped=skipped, unreachable=unreachable)

    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{label.replace(' ', '_')}_{now:%Y%m%d_%H%M}.txt"
    path.write_text(text + "\n", encoding="utf-8")
    return text, path, len(unreachable)
