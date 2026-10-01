"""Fetch a log from a vehicle over SSH. Key-based auth only, so it is cron-safe."""
import shlex
import subprocess

SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]


def fetch_log(host, remote_path, dest, tail_lines=None, timeout=120):
    """Copy remote_path to dest. With tail_lines, only the last N lines are pulled
    (much faster for huge logs). Returns (ok, message)."""
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if tail_lines:
            cmd = ["ssh", *SSH_OPTS, host, f"tail -n {int(tail_lines)} {shlex.quote(remote_path)}"]
            with open(dest, "wb") as out:
                r = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE, timeout=timeout)
        else:
            cmd = ["scp", "-q", *SSH_OPTS, f"{host}:{remote_path}", str(dest)]
            r = subprocess.run(cmd, stderr=subprocess.PIPE, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, type(e).__name__
    if r.returncode != 0:
        return False, f"exit {r.returncode}: {r.stderr.decode(errors='replace').strip()}"
    return True, ""
