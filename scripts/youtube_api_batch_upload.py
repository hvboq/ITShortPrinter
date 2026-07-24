from __future__ import annotations

import json
import os
import time
from pathlib import Path

import _bootstrap  # noqa: F401
from config import get_youtube_channel_config
from news.archive import mark_shorts_status
from news.duplicate_guard import (
    active_history_items,
    atomic_write_json,
    duplicate_reason,
    file_lock,
    load_history,
    write_history,
)
from project_paths import project_root
from youtube_api.uploader import clean_description, clean_title, upload_video, validate_visibility

ROOT = project_root()
UPLOAD_HISTORY = ROOT / "data" / "upload_history.json"
UPLOAD_HISTORY_LOCK = ROOT / "data" / "upload_history.lock"
SOURCE_LINK_LABEL = "원본 기사"
MAX_YOUTUBE_DESCRIPTION_LENGTH = 4500


def _read_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"INVALID_ENV_INT|name={name}|value={raw}|default={default}", flush=True)
        return default


def _item_rank(item: dict, fallback: int) -> int:
    try:
        return int(item.get("rank", fallback))
    except (TypeError, ValueError):
        return fallback


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
    with file_lock(UPLOAD_HISTORY_LOCK):
        history = load_history(UPLOAD_HISTORY)
        if duplicate_reason(entry, history):
            return
        history.append(entry)
        write_history(UPLOAD_HISTORY, history)


def _reservation_key(item: dict) -> str:
    return str(item.get("article_url") or item.get("article_title") or item.get("title") or item.get("video_path") or "")


def reserve_upload_item(item: dict, title: str) -> str | None:
    """Atomically reserve an article before YouTube API upload."""
    reservation_key = _reservation_key(item)
    reservation = {
        "article_title": item.get("article_title") or title,
        "article_url": item.get("article_url"),
        "article_id": item.get("article_id"),
        "source": item.get("source"),
        "title": title,
        "upload_status": "pending_upload",
        "reserved_at_unix": time.time(),
        "reservation_key": reservation_key,
    }
    with file_lock(UPLOAD_HISTORY_LOCK):
        history = active_history_items(load_history(UPLOAD_HISTORY))
        reason = duplicate_reason(item, history)
        if reason:
            return reason
        history.append(reservation)
        write_history(UPLOAD_HISTORY, history)
    return None


def finalize_upload_reservation(item: dict, result: dict) -> None:
    reservation_key = _reservation_key(item)
    with file_lock(UPLOAD_HISTORY_LOCK):
        history = load_history(UPLOAD_HISTORY)
        replaced = False
        for idx, existing in enumerate(history):
            if isinstance(existing, dict) and existing.get("reservation_key") == reservation_key:
                history[idx] = result
                replaced = True
                break
        if not replaced and not duplicate_reason(result, history):
            history.append(result)
        write_history(UPLOAD_HISTORY, history)


def clear_upload_reservation(item: dict) -> None:
    reservation_key = _reservation_key(item)
    with file_lock(UPLOAD_HISTORY_LOCK):
        history = [
            existing
            for existing in load_history(UPLOAD_HISTORY)
            if not (isinstance(existing, dict) and existing.get("reservation_key") == reservation_key)
        ]
        write_history(UPLOAD_HISTORY, history)


def _load_manifest(manifest_path: Path) -> list[dict]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Upload manifest must contain a list: {manifest_path}")
    for idx, item in enumerate(data, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Upload manifest item #{idx} is not an object")
        if "rank" not in item:
            item["rank"] = item.get("batch_index") or idx
    start_rank = _read_int_env("START_RANK", 1)
    end_rank = _read_int_env("END_RANK", 999)
    if end_rank < start_rank:
        print(
            f"INVALID_RANK_RANGE|start={start_rank}|end={end_rank}|using_empty_selection=1",
            flush=True,
        )
        return []
    selected = [
        item for item in data
        if start_rank <= _item_rank(item, 0) <= end_rank
    ]
    print("UPLOAD_RANK_RANGE=", start_rank, end_rank, "COUNT=", len(selected), flush=True)
    return selected


def _quality_failed(item: dict) -> bool:
    if item.get("placeholder_visuals_used") is True:
        return True
    if not _has_quality_fields(item):
        return os.environ.get("ALLOW_UNREVIEWED_UPLOADS", "").strip().lower() not in {"1", "true", "yes"}
    if item.get("review_quality_pass", True) is not True:
        return True
    if item.get("structure_quality_pass", True) is not True:
        return True
    return item.get("overall_quality_pass") is not True


def _has_quality_fields(item: dict) -> bool:
    return any(
        key in item
        for key in ("overall_quality_pass", "review_quality_pass", "structure_quality_pass")
    )


def _quality_failure_reason(item: dict) -> str:
    if item.get("placeholder_visuals_used") is True:
        return "placeholder_visuals_used"
    if not _has_quality_fields(item):
        return "quality_fields_missing"
    if "review_quality_pass" in item and item.get("review_quality_pass") is not True:
        return "review_quality_failed"
    if "structure_quality_pass" in item and item.get("structure_quality_pass") is not True:
        return "structure_quality_failed"
    if "overall_quality_pass" not in item:
        return "quality_fields_incomplete"
    return "overall_quality_failed"


def _skip_quality_failed_result(item: dict, video_path: str) -> dict:
    reason = _quality_failure_reason(item)
    return {
        "rank": item["rank"],
        "video_path": video_path,
        "article_title": item.get("article_title"),
        "article_url": item.get("article_url"),
        "article_id": item.get("article_id"),
        "source": item.get("source"),
        "skipped": True,
        "skip_reason": reason,
        "review_warnings": item.get("review_warnings", []),
        "structure_warnings": item.get("structure_warnings", []),
        "placeholder_visuals_used": item.get("placeholder_visuals_used", False),
        "placeholder_visual_reasons": item.get("placeholder_visual_reasons", []),
    }


def _skip_duplicate_result(item: dict, video_path: str, title: str, reason: str) -> dict:
    return {
        "rank": item["rank"],
        "video_path": video_path,
        "article_title": item.get("article_title"),
        "article_url": item.get("article_url"),
        "article_id": item.get("article_id"),
        "source": item.get("source"),
        "title": title,
        "skipped": True,
        "skip_reason": f"duplicate_{reason}",
    }


def _write_results(output_manifest: Path, results: list[dict]) -> None:
    atomic_write_json(output_manifest, results)


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
    visibility = validate_visibility(visibility)
    print(start_label, flush=True)
    print("UPLOAD_PROVIDER= youtube_api", flush=True)
    print("UPLOAD_SOURCE_MANIFEST=", str(source_manifest), flush=True)

    channel_config = get_youtube_channel_config()
    expected_channel_id = os.environ.get("EXPECTED_YOUTUBE_CHANNEL_ID", channel_config["id"])
    if expected_channel_id:
        print("EXPECTED_YOUTUBE_CHANNEL_ID=", expected_channel_id, flush=True)
    if visibility == "public":
        if os.environ.get("ALLOW_PUBLIC_UPLOAD", "").strip().lower() not in {"1", "true", "yes"}:
            raise RuntimeError("Refusing public upload without ALLOW_PUBLIC_UPLOAD=1")
        if not expected_channel_id:
            raise RuntimeError("Public uploads require YOUTUBE_CHANNEL_ID or EXPECTED_YOUTUBE_CHANNEL_ID")

    data = _load_manifest(source_manifest)
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    results = []

    for item in data:
        rank = item["rank"]
        video_path = str(Path(item.get("video_path", "")).resolve())
        if _quality_failed(item):
            result = _skip_quality_failed_result(item, video_path)
            results.append(result)
            _write_results(output_manifest, results)
            if update_archive:
                mark_shorts_status(
                    result,
                    "needs_review",
                    rank=rank,
                    video_path=video_path,
                )
            print(
                f"UPLOAD_{rank}_SKIP|reason={result['skip_reason']}|"
                f"review_warnings={','.join(map(str, item.get('review_warnings', [])))}|"
                f"structure_warnings={','.join(map(str, item.get('structure_warnings', [])))}",
                flush=True,
            )
            continue

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
        with file_lock(UPLOAD_HISTORY_LOCK):
            reason = duplicate_reason(item, load_history(UPLOAD_HISTORY))
        if reason:
            result = _skip_duplicate_result(item, video_path, title, reason)
            results.append(result)
            _write_results(output_manifest, results)
            print(
                f"UPLOAD_{rank}_SKIP_DUPLICATE|match={reason}|title={title}",
                flush=True,
            )
            continue
        print(f"UPLOAD_{rank}_START|provider=youtube_api|path={video_path}|title={title}", flush=True)

        reason = reserve_upload_item(item, title)
        if reason:
            result = _skip_duplicate_result(item, video_path, title, reason)
            results.append(result)
            _write_results(output_manifest, results)
            print(
                f"UPLOAD_{rank}_SKIP_DUPLICATE_BEFORE_API|match={reason}|title={title}",
                flush=True,
            )
            continue

        try:
            uploaded = upload_video(
                video_path=video_path,
                title=title,
                description=desc,
                visibility=visibility,
                notify_subscribers=os.environ.get("YOUTUBE_NOTIFY_SUBSCRIBERS", "").lower()
                in {"1", "true", "yes"},
                expected_channel_id=expected_channel_id,
            )
        except Exception:
            clear_upload_reservation(item)
            raise
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
        if update_history:
            finalize_upload_reservation(item, result)
        else:
            clear_upload_reservation(item)
        results.append(result)
        _write_results(output_manifest, results)
        if update_archive:
            mark_shorts_status(
                result,
                "uploaded",
                rank=rank,
                video_path=video_path,
                uploaded_url=result["uploaded_url"],
            )
        print(f"UPLOAD_{rank}_DONE|provider=youtube_api|url={result['uploaded_url']}", flush=True)

    print(done_label, flush=True)
    print("UPLOAD_MANIFEST=", str(output_manifest), flush=True)
    return results
