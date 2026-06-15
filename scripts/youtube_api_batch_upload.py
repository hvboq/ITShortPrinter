from __future__ import annotations

import json
import os
import time
from pathlib import Path

import _bootstrap  # noqa: F401
from config import get_youtube_channel_config
from news.archive import mark_shorts_status
from project_paths import project_root
from youtube_api.uploader import clean_description, clean_title, upload_video

ROOT = project_root()
UPLOAD_HISTORY = ROOT / "data" / "upload_history.json"
SOURCE_LINK_LABEL = "원본 기사"
MAX_YOUTUBE_DESCRIPTION_LENGTH = 4500


def build_upload_description(base_description: str, article_url: str | None) -> str:
    """Return a YouTube-safe description with the source article URL preserved.

    YouTube descriptions are capped by ``clean_description``. Keep the source
    link at the end so it is not accidentally truncated when generated copy is
    long.
    """
    base = clean_description(base_description)
    url = (article_url or "").strip()
    if not url:
        return base

    source_line = f"{SOURCE_LINK_LABEL}: {url}"
    if source_line in base:
        return clean_description(base)

    separator = "\n\n" if base else ""
    reserved = len(separator) + len(source_line)
    max_base_length = max(0, MAX_YOUTUBE_DESCRIPTION_LENGTH - reserved)
    base = base[:max_base_length].rstrip()
    separator = "\n\n" if base else ""
    return clean_description(f"{base}{separator}{source_line}")


def append_upload_history(entry: dict) -> None:
    try:
        history = (
            json.loads(UPLOAD_HISTORY.read_text(encoding="utf-8"))
            if UPLOAD_HISTORY.exists()
            else []
        )
        if not isinstance(history, list):
            history = []
    except Exception:
        history = []

    key = entry.get("article_url") or entry.get("uploaded_url") or entry.get("title")
    existing = {
        item.get("article_url") or item.get("uploaded_url") or item.get("title")
        for item in history
        if isinstance(item, dict)
    }
    if key not in existing:
        UPLOAD_HISTORY.parent.mkdir(parents=True, exist_ok=True)
        history.append(entry)
        UPLOAD_HISTORY.write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _load_manifest(manifest_path: Path) -> list[dict]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Upload manifest must contain a list: {manifest_path}")
    for idx, item in enumerate(data, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Upload manifest item #{idx} is not an object")
        if "rank" not in item:
            item["rank"] = item.get("batch_index") or idx
    start_rank = int(os.environ.get("START_RANK", "1"))
    end_rank = int(os.environ.get("END_RANK", "999"))
    selected = [
        item for item in data
        if start_rank <= int(item.get("rank", 0)) <= end_rank
    ]
    print("UPLOAD_RANK_RANGE=", start_rank, end_rank, "COUNT=", len(selected), flush=True)
    return selected


def upload_manifest_with_api(
    *,
    source_manifest: Path,
    output_manifest: Path,
    visibility: str,
    update_history: bool,
    update_archive: bool,
    start_label: str,
    done_label: str,
) -> list[dict]:
    print(start_label, flush=True)
    print("UPLOAD_PROVIDER= youtube_api", flush=True)
    print("UPLOAD_SOURCE_MANIFEST=", str(source_manifest), flush=True)

    channel_config = get_youtube_channel_config()
    expected_channel_id = os.environ.get("EXPECTED_YOUTUBE_CHANNEL_ID", channel_config["id"])
    if expected_channel_id:
        print("EXPECTED_YOUTUBE_CHANNEL_ID=", expected_channel_id, flush=True)

    data = _load_manifest(source_manifest)
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    results = []

    for item in data:
        rank = item["rank"]
        title = clean_title(
            item.get("metadata", {}).get("title") or item.get("article_title")
        )
        if not title:
            raise ValueError(f"Rank {rank} has no safe human-readable title")
        video_path = str(Path(item["video_path"]).resolve())
        desc = build_upload_description(
            item.get("metadata", {}).get("description") or "",
            item.get("article_url"),
        )
        print(f"UPLOAD_{rank}_START|provider=youtube_api|path={video_path}|title={title}", flush=True)

        uploaded = upload_video(
            video_path=video_path,
            title=title,
            description=desc,
            visibility=visibility,
            notify_subscribers=os.environ.get("YOUTUBE_NOTIFY_SUBSCRIBERS", "").lower()
            in {"1", "true", "yes"},
        )
        result = {
            "rank": rank,
            "video_path": video_path,
            "title": uploaded["title"],
            "description": uploaded["description"],
            "article_title": item.get("article_title"),
            "article_url": item.get("article_url"),
            "article_id": item.get("article_id"),
            "source": item.get("source"),
            "visibility": uploaded["visibility"],
            "video_id": uploaded["video_id"],
            "uploaded_url": uploaded["uploaded_url"],
            "source_video_path": item["video_path"],
            "uploaded_at_unix": time.time(),
            "upload_provider": "youtube_api",
        }
        results.append(result)
        output_manifest.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if update_archive:
            mark_shorts_status(
                result,
                "uploaded",
                rank=rank,
                video_path=video_path,
                uploaded_url=result["uploaded_url"],
            )
        if update_history:
            append_upload_history(result)
        print(f"UPLOAD_{rank}_DONE|provider=youtube_api|url={result['uploaded_url']}", flush=True)

    print(done_label, flush=True)
    print("UPLOAD_MANIFEST=", str(output_manifest), flush=True)
    return results
