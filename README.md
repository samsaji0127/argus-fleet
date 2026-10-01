# Argus

![tests](https://github.com/samsaji0127/argus-fleet/actions/workflows/tests.yml/badge.svg)

**Never-sleeping shift reports for robot fleets.** Argus turns raw error logs into a clean, Slack-ready shift report: trips and distance per vehicle, errors by category, how each was recovered, and repeat issues flagged.

Zero dependencies. Python 3.8+.

## Quick start

```bash
python -m argus demo                      # see a report from simulated data
python -m argus sample examples           # write example CSVs
python -m argus report examples/events.csv --trips examples/trips.csv --label "Night Run"
```

Or install the `argus` command:

```bash
pip install .
argus report events.csv --trips trips.csv --label "Morning Testing" --out report.txt
```

## Input format

`events.csv` (one row per error):

| column | required | notes |
|---|---|---|
| vehicle | yes | any ID |
| category | yes | matched case-insensitively |
| recovery | no | blank becomes "unrecorded" |
| timestamp | no | ISO format; used for the time window |

`trips.csv` (optional): `vehicle, trips, km`. Rows for the same vehicle are summed.

Malformed rows are skipped and counted in the report, never silently dropped.

## Output

```
*Night Run Report*
_01 Jan 22:25 → 02 Jan 09:11_

*Vehicles*
• *VEH-A*: 43 trips / 6.81 km
   ◦ 16 errors: Control Module ×5, CAN Drivers ×3, Camera ×2, ...
   ◦ Recovery: fleet mode switch ×6, reset pose ×5, power cycle ×4, ...

*Repeat issues*
• ⚠ VEH-A: Control Module occurred 5×

*Overall*
• 27 errors across 2 vehicle(s)
• Most common: Control Module (6)
```

Paste straight into Slack. `*bold*` and `_italic_` render natively.

## Automation

`argus run` fetches each vehicle's log over SSH, parses it with your rules, keeps the last N hours, and builds the report.

```bash
cp argus.example.json argus.json      # vehicles: name, host, log path
cp rules.example.json rules.json      # regex rules that match your log lines
python3 -m argus parse real.log --vehicle VEH-A    # check what the rules catch
python3 -m argus run --hours 8 --label "Morning Testing"
```

- **Rules are the only thing to tune.** Run `argus parse` on a real log, see which lines match, and edit `rules.json` until the categories look right. No code changes.
- **Key-based SSH only** (`BatchMode`), so it never hangs on a password prompt. Run `ssh user@host` once by hand first so the host key is trusted.
- **Unreachable vehicles are reported**, never silently dropped, and the exit code is `1` so cron or CI can alert.
- `--local` skips fetching and uses logs already in `data/`, handy for testing.
- Reports are also saved under `reports/` (git-ignored).

### Schedule it

```bash
crontab -e
```
```
# Morning shift 06:00-14:00, report at 14:05
5 14 * * * cd /path/to/argus-fleet && /usr/bin/python3 -m argus run --hours 8 --label "Morning Testing" >> data/cron.log 2>&1
# Night shift 22:00-06:00, report at 06:05
5 6 * * * cd /path/to/argus-fleet && /usr/bin/python3 -m argus run --hours 8 --label "Night Run" >> data/cron.log 2>&1
```

Cron has a minimal environment: use full paths, and use an SSH key without a passphrase (or an agent) for the fetch to work unattended. Your machine must be on the network that can reach the vehicles.

## Rolling it out safely

1. Run it on your own logs and post to a private test channel.
2. Shadow your manual report for a few shifts and compare the numbers.
3. Share with teammates, then switch over once the format is signed off.

Always review before posting. Keep real vehicle IDs and logs out of the repo (`data/`, `real/` and `*.log` are git-ignored).

## Tests

```bash
pip install pytest
pytest -q
```
