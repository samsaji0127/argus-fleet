import json
from datetime import datetime

import pytest

from argus.parser import load_rules, parse_log
from argus.run import run_pipeline

RULES = {
    "rules": [
        {"pattern": r"lidar.*timeout", "category": "LiDAR", "recovery": "power cycle"},
        {"pattern": r"(camera) disconnect", "category": r"\1 fault"},
        {"pattern": r"error", "category": "Other"},
    ]
}

LOG_A = """2026-10-01 07:00:00 INFO all good
2026-10-01 07:10:00 ERROR LiDAR read timeout
2026-10-01 07:20:00 WARN camera disconnect detected
2026-10-01 07:30:00 ERROR something odd
2026-09-30 01:00:00 ERROR LiDAR read timeout
"""


def setup(tmp_path, hosts=True):
    (tmp_path / "rules.json").write_text(json.dumps(RULES))
    veh = [{"name": "VEH-A", "log": "/x/a.log"}, {"name": "VEH-B", "log": "/x/b.log"}]
    if hosts:
        for v in veh:
            v["host"] = "user@h"
    (tmp_path / "argus.json").write_text(json.dumps({"vehicles": veh, "hours": 8}))
    return str(tmp_path / "argus.json")


def test_parse_rules_first_match_and_expand(tmp_path):
    (tmp_path / "r.json").write_text(json.dumps(RULES))
    events = parse_log(LOG_A.splitlines(), load_rules(tmp_path / "r.json"), "VEH-A")
    assert [e.category for e in events] == ["LiDAR", "camera fault", "Other", "LiDAR"]
    assert events[0].recovery == "power cycle" and events[1].recovery == "unrecorded"
    assert events[0].timestamp == datetime(2026, 10, 1, 7, 10)


def test_bad_regex_and_empty_rules(tmp_path):
    (tmp_path / "r.json").write_text(json.dumps({"rules": [{"pattern": "(", "category": "x"}]}))
    with pytest.raises(ValueError, match="invalid regex"):
        load_rules(tmp_path / "r.json")
    (tmp_path / "e.json").write_text(json.dumps({"rules": []}))
    with pytest.raises(ValueError, match="rules"):
        load_rules(tmp_path / "e.json")


def test_pipeline_window_and_clean_vehicle(tmp_path):
    cfg = setup(tmp_path)

    def fetcher(host, path, dest, tail):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(LOG_A if dest.name == "VEH-A.log" else "2026-10-01 07:00:00 INFO fine\n")
        return True, ""

    now = datetime(2026, 10, 1, 14, 0)
    text, path, bad = run_pipeline(cfg, label="Morning Testing", fetcher=fetcher, now=now)
    assert bad == 0 and path.exists()
    assert "3 errors" in text            # the 30 Sep event is outside the 8h window
    assert "VEH-B*" in text and "No errors" in text


def test_unreachable_vehicle_reported_not_hidden(tmp_path):
    cfg = setup(tmp_path)

    def fetcher(host, path, dest, tail):
        if dest.name == "VEH-B.log":
            return False, "exit 255: secret-hostname refused"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(LOG_A)
        return True, ""

    text, _, bad = run_pipeline(cfg, fetcher=fetcher, now=datetime(2026, 10, 1, 14, 0))
    assert bad == 1
    assert "*Unreachable*" in text and "VEH-B" in text
    assert "secret-hostname" not in text   # error detail never leaks into the Slack text


def test_local_mode(tmp_path):
    cfg = setup(tmp_path, hosts=False)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "VEH-A.log").write_text(LOG_A)
    text, _, bad = run_pipeline(cfg, local=True, now=datetime(2026, 10, 1, 14, 0))
    assert bad == 1                       # VEH-B has no local log
    assert "VEH-A" in text and "no local log found" in text


def _rules(tmp_path, **extra):
    cfg = {
        "timestamp": [
            {"regex": r"^\[?(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})", "format": "iso"},
            {"regex": r"^[IWEF](\d{4} \d{2}:\d{2}:\d{2}\.\d+)", "format": "%m%d %H:%M:%S.%f"},
        ],
        "rules": [
            {"pattern": r"runaway_exception.*Motor(left|right)_encoder", "category": r"Motor Runaway (\1)"},
            {"pattern": r"motor_utils\.cpp.*publishing exception", "category": "Motor Exception"},
        ],
    }
    cfg.update(extra)
    (tmp_path / "r.json").write_text(json.dumps(cfg))
    return load_rules(tmp_path / "r.json")


def test_glog_timestamp_without_year(tmp_path):
    rules = _rules(tmp_path)
    line = "I1001 12:20:30.123456  1234 motor_utils.cpp:55] publishing exception msg"
    ev = parse_log([line], rules, "V", now=datetime(2026, 10, 1, 14, 0))
    assert ev[0].category == "Motor Exception"
    assert ev[0].timestamp == datetime(2026, 10, 1, 12, 20, 30, 123456)


def test_yearless_timestamp_across_new_year(tmp_path):
    rules = _rules(tmp_path)
    line = "I1231 23:00:00.000000  1 motor_utils.cpp:5] publishing exception msg"
    ev = parse_log([line], rules, "V", now=datetime(2027, 1, 1, 1, 0))
    assert ev[0].timestamp.year == 2026


def test_group_reference_in_category(tmp_path):
    rules = _rules(tmp_path)
    line = "2026-10-01 12:00:00 - INFO [p.py:1] runaway_exception by 3, runaway: Motorright_encoder overshoot"
    assert parse_log([line], rules, "V")[0].category == "Motor Runaway (right)"


def test_burst_merging(tmp_path):
    rules = _rules(tmp_path, merge_gap_s=60)
    mk = lambda s: f"2026-10-01 07:{s} - INFO [p.py:1] runaway_exception by 3, runaway: Motorleft_encoder overshoot"
    lines = [mk("00:00"), mk("00:20"), mk("00:50"), mk("05:00")]
    assert len(parse_log(lines, rules, "V")) == 2   # one burst, then a separate incident
    assert len(parse_log(lines, _rules(tmp_path), "V")) == 4   # no merging by default
