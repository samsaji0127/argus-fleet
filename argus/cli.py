"""Command line: argus report | run | parse | demo | sample."""
import argparse
import csv
import sys

from .loader import read_events, read_trips
from .parser import load_rules, parse_log
from .report import render_slack, summarize
from .run import run_pipeline
from .simulate import demo_events, demo_trips, write_examples


def _emit(text, out):
    print(text)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"\n(saved to {out})", file=sys.stderr)


def cmd_report(args):
    try:
        events, skipped = read_events(args.events)
        trips, trip_skipped = read_trips(args.trips) if args.trips else ({}, 0)
    except (OSError, ValueError) as e:
        print(f"argus: {e}", file=sys.stderr)
        return 2
    text = render_slack(summarize(events, trips), label=args.label, events=events,
                        repeat_threshold=args.repeat_threshold,
                        skipped=skipped + trip_skipped)
    _emit(text, args.out)
    return 0


def cmd_run(args):
    try:
        text, path, bad = run_pipeline(args.config, hours=args.hours, label=args.label, local=args.local)
    except (OSError, ValueError) as e:
        print(f"argus: {e}", file=sys.stderr)
        return 2
    print(text)
    print(f"\n(saved to {path})", file=sys.stderr)
    return 1 if bad else 0


def cmd_parse(args):
    try:
        rules = load_rules(args.rules)
        with open(args.log, encoding="utf-8", errors="replace") as f:
            events = parse_log(f, rules, args.vehicle)
    except (OSError, ValueError) as e:
        print(f"argus: {e}", file=sys.stderr)
        return 2
    out = open(args.out, "w", newline="", encoding="utf-8") if args.out else sys.stdout
    w = csv.writer(out)
    w.writerow(["timestamp", "vehicle", "category", "recovery"])
    for e in events:
        w.writerow([e.timestamp.isoformat(sep=" ") if e.timestamp else "", e.vehicle, e.category, e.recovery])
    if args.out:
        out.close()
    print(f"argus: {len(events)} event(s) parsed", file=sys.stderr)
    return 0


def cmd_demo(args):
    events = demo_events()
    _emit(render_slack(summarize(events, demo_trips()), label=args.label, events=events), None)
    return 0


def cmd_sample(args):
    write_examples(args.dir)
    print(f"Wrote {args.dir}/events.csv and {args.dir}/trips.csv")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="argus", description="Never-sleeping shift reports for robot fleets.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("report", help="build a report from CSV files")
    r.add_argument("events", help="events CSV: vehicle, category [, recovery, timestamp]")
    r.add_argument("--trips", help="trips CSV: vehicle, trips, km")
    r.add_argument("--label", default="Shift", help='report title, e.g. "Night Run"')
    r.add_argument("--repeat-threshold", type=int, default=2)
    r.add_argument("--out", help="also save the report to this file")
    r.set_defaults(fn=cmd_report)

    u = sub.add_parser("run", help="automation: fetch logs, parse, report")
    u.add_argument("--config", default="argus.json")
    u.add_argument("--hours", type=float, help="only events from the last N hours")
    u.add_argument("--label", help="report title (overrides config)")
    u.add_argument("--local", action="store_true", help="skip fetching; use logs already in data/")
    u.set_defaults(fn=cmd_run)

    a = sub.add_parser("parse", help="turn a raw log into events CSV using a rules file")
    a.add_argument("log")
    a.add_argument("--rules", default="rules.json")
    a.add_argument("--vehicle", required=True)
    a.add_argument("--out", help="write CSV here (default: stdout)")
    a.set_defaults(fn=cmd_parse)

    d = sub.add_parser("demo", help="print a report from simulated data")
    d.add_argument("--label", default="Demo Shift")
    d.set_defaults(fn=cmd_demo)

    s = sub.add_parser("sample", help="write example CSV files")
    s.add_argument("dir", nargs="?", default="examples")
    s.set_defaults(fn=cmd_sample)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
