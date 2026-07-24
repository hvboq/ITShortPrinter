from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from youtube_api.auth import CHANNEL_UPLOAD_SCOPES, UPLOAD_SCOPES, get_credentials, youtube_data_service

HEX_UUID_TITLE_RE = re.compile(
    r"^(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{8}[- ][0-9a-fA-F]{4}[- ][0-9a-fA-F]{4}[- ][0-9a-fA-F]{4}[- ][0-9a-fA-F]{12})(?:\.[A-Za-z0-9]+)?$"
)


def clean_title(value: str) -> str:
    title = re.sub(r"\s+", " ", (value or "")).strip()
    if is_hex_uuid_title(title):
        return ""
    return title[:95]


def clean_description(value: str) -> str:
    return (value or "").strip()[:4500]


def is_hex_uuid_title(value: str) -> bool:
    compact = re.sub(r"\s+", " ", (value or "")).strip()
    return bool(HEX_UUID_TITLE_RE.match(compact))


def validate_visibility(visibility: str) -> str:
    normalized = str(visibility or "").strip().lower()
    if normalized not in {"private", "unlisted", "public"}:
        raise ValueError("visibility must be private, unlisted, or public")
    return normalized


def build_video_body(
    title: str,
    description: str = "",
    visibility: str = "unlisted",
    tags: list[str] | None = None,
    category_id: str = "28",
    made_for_kids: bool = False,
) -> dict[str, Any]:
    title = clean_title(title)
    if not title:
        raise ValueError("A human-readable non-UUID title is required for YouTube upload")

    body: dict[str, Any] = {
        "snippet": {
            "title": title,
            "description": clean_description(description),
            "categoryId": str(category_id or "28"),
        },
        "status": {
            "privacyStatus": validate_visibility(visibility),
            "selfDeclaredMadeForKids": bool(made_for_kids),
        },
    }
    if tags:
        body["snippet"]["tags"] = [str(tag)[:100] for tag in tags if str(tag).strip()]
    return body


def _authorized_channel_ids(youtube_service) -> set[str]:
    response = youtube_service.channels().list(part="id", mine=True).execute()
    return {
        str(item.get("id", "")).strip()
        for item in response.get("items", [])
        if str(item.get("id", "")).strip()
    }


def _ensure_expected_channel(youtube_service, expected_channel_id: str) -> None:
    expected = str(expected_channel_id or "").strip()
    if not expected:
        return
    channel_ids = _authorized_channel_ids(youtube_service)
    if expected not in channel_ids:
        found = ",".join(sorted(channel_ids)) or "none"
        raise RuntimeError(
            f"YouTube OAuth token is not authorized for expected channel {expected}; found {found}"
        )


def _require_expected_channel_for_visibility(visibility: str, expected_channel_id: str) -> None:
    if validate_visibility(visibility) == "public" and not str(expected_channel_id or "").strip():
        raise ValueError("Public uploads require an expected YouTube channel id")


def upload_video(
    video_path: str,
    title: str,
    description: str = "",
    visibility: str = "unlisted",
    *,
    tags: list[str] | None = None,
    category_id: str = "28",
    made_for_kids: bool = False,
    notify_subscribers: bool = False,
    expected_channel_id: str = "",
    youtube_service=None,
) -> dict[str, Any]:
    """Upload a video through YouTube Data API v3 videos.insert."""
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Upload video not found: {path}")

    _require_expected_channel_for_visibility(visibility, expected_channel_id)

    from googleapiclient.http import MediaFileUpload

    scopes = CHANNEL_UPLOAD_SCOPES if expected_channel_id else UPLOAD_SCOPES
    youtube = youtube_service or youtube_data_service(
        get_credentials(scopes=scopes, interactive=False)
    )
    _ensure_expected_channel(youtube, expected_channel_id)
    body = build_video_body(
        title=title,
        description=description,
        visibility=visibility,
        tags=tags,
        category_id=category_id,
        made_for_kids=made_for_kids,
    )
    media = MediaFileUpload(str(path), mimetype="video/*", resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
        notifySubscribers=bool(notify_subscribers),
    )
    response = request.execute()
    video_id = str(response.get("id", "")).strip()
    if not video_id:
        raise RuntimeError(f"YouTube API upload did not return a video id: {response}")

    return {
        "video_id": video_id,
        "uploaded_url": f"https://youtu.be/{video_id}",
        "response": response,
        "title": body["snippet"]["title"],
        "description": body["snippet"]["description"],
        "visibility": body["status"]["privacyStatus"],
    }
