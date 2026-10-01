import pytest

from argus.cli import main
from argus.loader import read_events, read_trips
from argus.report import find_repeats, render_slack, summarize


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


EVENTS = """timestamp,vehicle,category,recovery
2026-01-01 22:00,VEH-A,Device Monitor,power cycle
2026-01-01 23:00,VEH-A,device monitor,power cycle
2026-01-02 01:30,VEH-A,Camera,fleet mode switch
2026-01-02 02:00,VEH-B,LiDAR,
,,,
2026-01-02 03:00,VEH-B,  Camera  ,manual switch
"""


def test_counts_and_case_insensitive_categories(tmp_path):
    events, skipped = read_events(write(tmp_path, "e.csv", EVENTS))
    s = summarize(events)
    assert skipped == 1
    assert s["VEH-A"].errors["Device Monitor"] == 2
    assert s["VEH-A"].total == 3 and s["VEH-B"].total == 2


def test_missing_recovery_is_unrecorded(tmp_path):
    events, _ = read_events(write(tmp_path, "e.csv", EVENTS))
    assert summarize(events)["VEH-B"].recoveries["unrecorded"] == 1


def test_repeats_flagged(tmp_path):
    events, _ = read_events(write(tmp_path, "e.csv", EVENTS))
    assert find_repeats(summarize(events)) == [("VEH-A", "Device Monitor", 2)]


def test_trips_added_and_clean_vehicle_listed(tmp_path):
    events, _ = read_events(write(tmp_path, "e.csv", EVENTS))
    trips, _ = read_trips(write(tmp_path, "t.csv", "vehicle,trips,km\nVEH-A,10,1.5\nVEH-A,5,0.5\nVEH-C,7,2\n"))
    s = summarize(events, trips)
    assert (s["VEH-A"].trips, s["VEH-A"].km) == (15, 2.0)
    assert s["VEH-C"].total == 0
    text = render_slack(s, label="Night Run", events=events)
    assert "*Night Run Report*" in text
    assert "VEH-C*: 7 trips / 2.00 km" in text and "No errors" in text
    assert "Device Monitor occurred 2×" in text


def test_bad_trip_rows_skipped(tmp_path):
    trips, skipped = read_trips(write(tmp_path, "t.csv", "vehicle,trips,km\nVEH-A,abc,1\nVEH-B,3,1.0\n"))
    assert skipped == 1 and list(trips) == ["VEH-B"]


def test_missing_column_is_clear_error(tmp_path):
    with pytest.raises(ValueError, match="missing required column 'category'"):
        read_events(write(tmp_path, "e.csv", "vehicle,error\nA,x\n"))


def test_cli_report_and_missing_file(tmp_path, capsys):
    path = write(tmp_path, "e.csv", EVENTS)
    assert main(["report", path, "--label", "Night Run"]) == 0
    assert "Night Run Report" in capsys.readouterr().out
    assert main(["report", str(tmp_path / "nope.csv")]) == 2


def test_demo_runs(capsys):
    assert main(["demo"]) == 0
    assert "27 errors" in capsys.readouterr().out
