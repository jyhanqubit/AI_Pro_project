"""mypy ratchet: the known type-error count may go down, never up.

The repository carries type debt that is too large to clear in one change (see README >
검증 하네스). An advisory mypy step lets that debt grow unnoticed; a hard gate would block every
change until it is cleared. The ratchet is the middle ground used by most large Python
codebases: ``config/mypy_baseline.json`` records the accepted error count, this script fails when
a run exceeds it, and asks you to lower the baseline when a run comes in under it (so the
improvement is locked in).

Usage::

    python -m scripts.mypy_ratchet            # gate (CI, make check)
    python -m scripts.mypy_ratchet --update   # write the current count as the new baseline
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "config" / "mypy_baseline.json"
_SUMMARY = re.compile(r"Found (\d+) errors? in \d+ files?")


def run_mypy() -> tuple[int, str]:
    """Run mypy on the repository; return (error count, raw output)."""
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout + proc.stderr
    if proc.returncode == 0:
        return 0, out
    m = _SUMMARY.search(out)
    if m is None:
        # A crash or an unparsable summary is not "zero errors" — surface it loudly.
        raise RuntimeError(
            f"could not read the mypy summary (exit {proc.returncode}):\n{out[-2000:]}"
        )
    return int(m.group(1)), out


def load_baseline() -> int:
    return int(json.loads(BASELINE.read_text(encoding="utf-8"))["max_errors"])


def write_baseline(count: int) -> None:
    BASELINE.write_text(
        json.dumps(
            {
                "max_errors": count,
                "note": (
                    "Accepted mypy error count (scripts/mypy_ratchet.py). May only go down: "
                    "a run above this number fails, a run below asks you to lower it."
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--update", action="store_true", help="record the current count as the baseline"
    )
    args = parser.parse_args(argv)

    count, out = run_mypy()
    if args.update:
        write_baseline(count)
        print(f"mypy ratchet: baseline set to {count}")
        return 0

    baseline = load_baseline()
    if count > baseline:
        print(out[-4000:])
        print(
            f"mypy ratchet: FAIL — {count} errors, baseline allows {baseline}. New type errors were introduced."
        )
        return 1
    if count < baseline:
        print(
            f"mypy ratchet: {count} errors, below the baseline of {baseline}. Lock the improvement in: "
            "`python -m scripts.mypy_ratchet --update` and commit config/mypy_baseline.json."
        )
        return 1
    print(f"mypy ratchet: PASS — {count} errors, at the baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
