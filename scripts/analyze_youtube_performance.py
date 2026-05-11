#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from youtube_api.performance import collect_performance_report, write_report_files  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect YouTube Shorts performance data and write analysis-ready reports.")
    parser.add_argument("--days", type=int, default=28, help="Analytics lookback window in complete days. Default: 28")
    parser.add_argument("--max-videos", type=int, default=50, help="Recent uploads to include. Default: 50")
    parser.add_argument("--json-only", action="store_true", help="Print compact JSON status only after writing files.")
    args = parser.parse_args()

    report = collect_performance_report(days=args.days, max_videos=args.max_videos)
    paths = write_report_files(report)
    status = {
        "ok": True,
        "paths": paths,
        "channel": report["channel"],
        "analysis_window": report["analysis_window"],
        "totals": report["insights"]["totals"],
        "top_by_views": [
            {
                "video_id": v["video_id"],
                "title": v["title"],
                "period_views": v["analytics_window"]["views"],
                "public_lifetime_views": v["views_total_public"],
                "retention_signal_percentage": round(v["analytics_window"]["retention_signal_percentage"], 2),
                "net_subscribers": v["analytics_window"]["net_subscribers"],
            }
            for v in report["insights"]["top_by_views"][:5]
        ],
        "scope_warning_count": len(report["insights"].get("scope_warnings", [])),
    }
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if not args.json_only:
        print(f"\nMarkdown report: {paths['markdown']}")
        print(f"JSON report: {paths['json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
