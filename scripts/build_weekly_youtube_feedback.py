#!/usr/bin/env python3
"""Build conservative weekly runtime weights from captured 48-hour snapshots."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config import get_youtube_feedback_config  # noqa: E402
from youtube_api.feedback import build_weekly_feedback, load_json, write_json_atomic  # noqa: E402

DEFAULT_INPUT = PROJECT_ROOT / "data" / "youtube_48h_performance.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "youtube_weekly_feedback.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build bounded weekly YouTube topic feedback weights.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="48-hour snapshot JSON path.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Feedback JSON output path.")
    parser.add_argument("--days", type=int, default=7, help="Observed snapshot lookback, default 7 days.")
    parser.add_argument("--now", help="UTC ISO timestamp override for fixture/testing runs.")
    args = parser.parse_args(argv)

    snapshots = load_json(args.input, [])
    if not isinstance(snapshots, list):
        parser.error("input must be a JSON array")
    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cutoff = now.astimezone(timezone.utc) - timedelta(days=max(1, min(args.days, 31)))
    weekly = []
    for row in snapshots:
        if not isinstance(row, dict):
            continue
        try:
            observed = datetime.fromisoformat(str(row.get("observed_at", "")).replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if observed.astimezone(timezone.utc) >= cutoff:
            weekly.append(row)

    result = build_weekly_feedback(weekly, **get_youtube_feedback_config())
    result["window"] = {
        "days": max(1, min(args.days, 31)),
        "start_at": cutoff.isoformat(),
        "end_at": now.astimezone(timezone.utc).isoformat(),
    }
    write_json_atomic(args.output, result)
    print(json.dumps({
        "ok": True,
        "output": str(args.output),
        "eligible_sample_count": result["eligible_sample_count"],
        "runtime_weights": result["runtime_weights"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
