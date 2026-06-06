from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    # Force the dedicated product-launch collector path regardless of the caller's
    # environment.  The generic hourly script still handles rendering/uploading,
    # locks, manifests, and channel guards.
    os.environ["SHORTS_JOB_TOPIC"] = "product_launch"
    os.environ.setdefault("NEWS_LIMIT", "120")

    from scripts.run_two_hour_short_job import main as run_hourly_job

    return run_hourly_job()


if __name__ == "__main__":
    raise SystemExit(main())
