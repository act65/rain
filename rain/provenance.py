"""Provenance stamp for experiment result files.

Every result file records the commit (and uncommitted paths) it came from, so a
number and the code that produced it can be compared without a rerun.

Usage
-----
    from rain.provenance import run_provenance
    json.dump({"provenance": run_provenance(), "rows": rows}, f)

Everything is best-effort: on a machine with no git, no repo, or no network the
call still returns a dict rather than raising, because a provenance stamp must
never be the reason an eight-hour run fails to write its output.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["run_provenance", "git_commit", "git_dirty"]

_REPO = Path(__file__).resolve().parents[1]


def _git(*args, cwd=None) -> str | None:
    """Run a git command, returning stripped stdout or None on any failure."""
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=str(cwd or _REPO),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def git_commit(short: bool = False) -> str | None:
    """Current HEAD, or None if this is not a git checkout."""
    args = ("rev-parse", "--short", "HEAD") if short else ("rev-parse", "HEAD")
    return _git(*args)


def git_dirty() -> bool | None:
    """True if the working tree has uncommitted changes; None if unknown.

    This matters more than the commit for an experiment tree, where the usual
    state is "HEAD plus edits" and the commit alone would be misleading.
    """
    out = _git("status", "--porcelain")
    return None if out is None else bool(out)


def _dirty_paths(limit: int = 40) -> list[str] | None:
    """Which paths are dirty, so a stale result can be diagnosed, not just flagged."""
    out = _git("status", "--porcelain")
    if out is None:
        return None
    paths = [line[3:] for line in out.splitlines() if line[3:]]
    return sorted(paths)[:limit]


def _package_version(name: str) -> str | None:
    try:
        module = __import__(name)
    except Exception:
        return None
    return getattr(module, "__version__", None)


def run_provenance(extra: dict | None = None) -> dict:
    """A dict describing what produced this result.

    Fields are all optional in the sense that any of them may be ``None``; the
    call itself never raises.
    """
    stamp = {
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": git_commit(),
        "commit_short": git_commit(short=True),
        "dirty": git_dirty(),
        "dirty_paths": _dirty_paths(),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "python": sys.version.split()[0],
        "host": platform.node(),
    }
    # Jobs run on a machine without the git checkout pass the stamp of the tree they were
    # synced from through the environment (see experiments/README.md).
    if stamp["commit"] is None and os.environ.get("RAIN_COMMIT"):
        stamp["commit"] = os.environ["RAIN_COMMIT"]
        stamp["commit_short"] = stamp["commit"][:7]
        stamp["dirty"] = os.environ.get("RAIN_DIRTY") == "1"
        stamp["dirty_paths"] = "not recorded (stamp passed through the environment)"
    if extra:
        stamp.update(extra)
    return stamp
