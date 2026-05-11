from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from youtube_api.auth import get_credentials, youtube_analytics_service, youtube_data_service

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_HISTORY_PATH = PROJECT_ROOT / "data" / "upload_history.json"
REPORTS_DIR = PROJECT_ROOT / "reports" / "youtube"
EXPECTED_CHANNEL_ID = "UCcDkCUSZbX6EUPIqtVhRGyQ"

VIDEO_ID_RE = re.compile(r"(?:shorts/|watch\?v=|youtu\.be/)([A-Za-z0-9_-]{6,})")
ISO_DURATION_RE = re.compile(
    r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?"
)


def parse_video_id(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{6,}", value):
        return value
    match = VIDEO_ID_RE.search(value)
    return match.group(1) if match else None


def parse_iso8601_duration_seconds(duration: str | None) -> int:
    if not duration:
        return 0
    match = ISO_DURATION_RE.fullmatch(duration)
    if not match:
        return 0
    parts = {k: int(v or 0) for k, v in match.groupdict().items()}
    return (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_upload_history(path: Path = UPLOAD_HISTORY_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def upload_history_by_video_id(history: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for item in history:
        vid = parse_video_id(item.get("uploaded_url"))
        if vid:
            mapped[vid] = item
    return mapped


def get_channel_summary(youtube=None) -> dict[str, Any]:
    youtube = youtube or youtube_data_service()
    response = youtube.channels().list(part="id,snippet,statistics,contentDetails", mine=True).execute()
    channels = response.get("items", [])
    if not channels:
        raise RuntimeError("No YouTube channel returned for authorized account.")
    active = None
    for item in channels:
        if item.get("id") == EXPECTED_CHANNEL_ID:
            active = item
            break
    active = active or channels[0]
    snippet = active.get("snippet", {})
    stats = active.get("statistics", {})
    related = active.get("contentDetails", {}).get("relatedPlaylists", {})
    return {
        "id": active.get("id"),
        "title": snippet.get("title"),
        "customUrl": snippet.get("customUrl"),
        "statistics": {
            "viewCount": to_int(stats.get("viewCount")),
            "subscriberCount": to_int(stats.get("subscriberCount")),
            "videoCount": to_int(stats.get("videoCount")),
            "hiddenSubscriberCount": bool(stats.get("hiddenSubscriberCount", False)),
        },
        "uploads_playlist": related.get("uploads"),
        "expected_channel_match": active.get("id") == EXPECTED_CHANNEL_ID,
    }


def list_recent_upload_video_ids(youtube, uploads_playlist: str, max_results: int = 50) -> list[str]:
    ids: list[str] = []
    page_token = None
    while len(ids) < max_results:
        response = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist,
            maxResults=min(50, max_results - len(ids)),
            pageToken=page_token,
        ).execute()
        for item in response.get("items", []):
            vid = item.get("contentDetails", {}).get("videoId")
            if vid:
                ids.append(vid)
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return ids


def get_videos(youtube, video_ids: list[str]) -> list[dict[str, Any]]:
    videos: list[dict[str, Any]] = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        if not chunk:
            continue
        response = youtube.videos().list(
            part="id,snippet,contentDetails,statistics,status",
            id=",".join(chunk),
            maxResults=50,
        ).execute()
        videos.extend(response.get("items", []))
    order = {vid: idx for idx, vid in enumerate(video_ids)}
    videos.sort(key=lambda item: order.get(item.get("id"), 999999))
    return videos


def query_video_analytics(analytics, start_date: date, end_date: date) -> dict[str, dict[str, Any]]:
    metrics = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost"
    response = analytics.reports().query(
        ids="channel==MINE",
        startDate=start_date.isoformat(),
        endDate=end_date.isoformat(),
        metrics=metrics,
        dimensions="video",
        sort="-views",
        maxResults=200,
    ).execute()
    headers = [h.get("name") for h in response.get("columnHeaders", [])]
    rows = response.get("rows", [])
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(zip(headers, row))
        video_id = item.pop("video", None)
        if video_id:
            result[video_id] = item
    return result


def query_daily_analytics(analytics, start_date: date, end_date: date) -> list[dict[str, Any]]:
    metrics = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost"
    response = analytics.reports().query(
        ids="channel==MINE",
        startDate=start_date.isoformat(),
        endDate=end_date.isoformat(),
        metrics=metrics,
        dimensions="day",
        sort="day",
    ).execute()
    headers = [h.get("name") for h in response.get("columnHeaders", [])]
    return [dict(zip(headers, row)) for row in response.get("rows", [])]


def classify_topic(title: str, description: str = "") -> dict[str, Any]:
    text = f"{title} {description}".lower()
    rules = [
        ("smartphone/foldable", ["스마트폰", "폴드", "fold", "phone", "razr", "honor", "pixel", "galaxy", "iphone"]),
        ("chip/pc/semiconductor", ["cpu", "gpu", "amd", "인텔", "intel", "qualcomm", "칩", "반도체", "컴퓨텍스", "pc"]),
        ("wearable/accessory", ["watch", "워치", "wearable", "밴드", "loop"]),
        ("gaming/emulation", ["게임", "emulat", "ps2", "에뮬"]),
        ("ai/software", ["openai", "chatgpt", "ai", "인공지능", "소프트웨어"]),
    ]
    matched = [label for label, keywords in rules if any(k in text for k in keywords)]
    allowed_fit = "ai/software" not in matched
    return {
        "topic_categories": matched or ["other_hardware_or_it"],
        "fits_current_channel_scope": allowed_fit,
    }


def normalize_video(item: dict[str, Any], analytics_by_video: dict[str, dict[str, Any]], history_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    video_id = item.get("id")
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    content = item.get("contentDetails", {})
    status = item.get("status", {})
    duration_seconds = parse_iso8601_duration_seconds(content.get("duration"))
    title = snippet.get("title", "")
    description = snippet.get("description", "")
    analytics = analytics_by_video.get(video_id, {})
    has_analytics_data = video_id in analytics_by_video
    views = to_int(analytics.get("views")) if has_analytics_data else 0
    estimated_minutes = to_float(analytics.get("estimatedMinutesWatched"))
    avg_duration = to_float(analytics.get("averageViewDuration"))
    avg_pct = to_float(analytics.get("averageViewPercentage"))
    subscribers_gained = to_int(analytics.get("subscribersGained"))
    subscribers_lost = to_int(analytics.get("subscribersLost"))
    net_subscribers = subscribers_gained - subscribers_lost
    retention_signal = avg_pct if avg_pct else ((avg_duration / duration_seconds * 100) if duration_seconds else 0.0)
    local_history = history_by_id.get(video_id, {})
    topic = classify_topic(title, description)
    return {
        "video_id": video_id,
        "url": f"https://youtube.com/shorts/{video_id}",
        "title": title,
        "published_at": snippet.get("publishedAt"),
        "duration_seconds": duration_seconds,
        "privacy_status": status.get("privacyStatus"),
        "made_for_kids": status.get("madeForKids"),
        "views_total_public": to_int(stats.get("viewCount")),
        "likes_total_public": to_int(stats.get("likeCount")),
        "comments_total_public": to_int(stats.get("commentCount")),
        "analytics_window": {
            "views": views,
            "estimated_minutes_watched": estimated_minutes,
            "average_view_duration_seconds": avg_duration,
            "average_view_percentage": avg_pct,
            "subscribers_gained": subscribers_gained,
            "subscribers_lost": subscribers_lost,
            "net_subscribers": net_subscribers,
            "retention_signal_percentage": retention_signal,
            "has_analytics_data": has_analytics_data,
        },
        "local_upload_history": {
            "rank": local_history.get("rank"),
            "article_title": local_history.get("article_title"),
            "article_url": local_history.get("article_url"),
            "source": local_history.get("source"),
            "uploaded_at_unix": local_history.get("uploaded_at_unix"),
        },
        **topic,
    }


def build_insights(videos: list[dict[str, Any]], daily: list[dict[str, Any]]) -> dict[str, Any]:
    ranked_by_views = sorted(videos, key=lambda v: v["analytics_window"]["views"], reverse=True)
    ranked_by_retention = sorted(videos, key=lambda v: v["analytics_window"]["retention_signal_percentage"], reverse=True)
    ranked_by_subs = sorted(videos, key=lambda v: v["analytics_window"]["net_subscribers"], reverse=True)
    total_views = sum(v["analytics_window"]["views"] for v in videos)
    total_public_views = sum(v["views_total_public"] for v in videos)
    videos_with_analytics = sum(1 for v in videos if v["analytics_window"].get("has_analytics_data"))
    total_minutes = sum(v["analytics_window"]["estimated_minutes_watched"] for v in videos)
    total_net_subs = sum(v["analytics_window"]["net_subscribers"] for v in videos)
    out_of_scope = [v for v in videos if not v.get("fits_current_channel_scope")]
    categories: dict[str, dict[str, Any]] = {}
    for v in videos:
        for cat in v.get("topic_categories", ["unknown"]):
            bucket = categories.setdefault(cat, {"videos": 0, "views": 0, "net_subscribers": 0})
            bucket["videos"] += 1
            bucket["views"] += v["analytics_window"]["views"]
            bucket["net_subscribers"] += v["analytics_window"]["net_subscribers"]
    return {
        "totals": {
            "videos_analyzed": len(videos),
            "videos_with_analytics_rows": videos_with_analytics,
            "period_views_from_analytics": total_views,
            "public_lifetime_views_for_listed_videos": total_public_views,
            "estimated_minutes_watched": round(total_minutes, 2),
            "net_subscribers": total_net_subs,
        },
        "top_by_views": ranked_by_views[:10],
        "top_by_retention": ranked_by_retention[:10],
        "top_by_subscribers": ranked_by_subs[:10],
        "category_summary": categories,
        "scope_warnings": [
            {"video_id": v["video_id"], "title": v["title"], "categories": v["topic_categories"]}
            for v in out_of_scope
        ],
        "daily_rows": daily,
    }


def collect_performance_report(days: int = 28, max_videos: int = 50) -> dict[str, Any]:
    creds = get_credentials(interactive=False)
    youtube = youtube_data_service(creds)
    analytics = youtube_analytics_service(creds)
    channel = get_channel_summary(youtube)
    if not channel.get("expected_channel_match"):
        raise RuntimeError(f"Authorized channel mismatch: {channel}")
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=max(days - 1, 0))
    video_ids = list_recent_upload_video_ids(youtube, channel["uploads_playlist"], max_results=max_videos)
    videos_raw = get_videos(youtube, video_ids)
    analytics_by_video = query_video_analytics(analytics, start_date, end_date)
    daily = query_daily_analytics(analytics, start_date, end_date)
    history_by_id = upload_history_by_video_id(load_upload_history())
    videos = [normalize_video(item, analytics_by_video, history_by_id) for item in videos_raw]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_window": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "days": days},
        "channel": channel,
        "videos": videos,
        "insights": build_insights(videos, daily),
    }


def write_report_files(report: dict[str, Any], output_dir: Path | None = None) -> dict[str, str]:
    output_dir = output_dir or REPORTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"youtube_performance_{stamp}.json"
    md_path = output_dir / f"youtube_performance_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown_report(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def render_video_table(videos: list[dict[str, Any]], limit: int = 10) -> str:
    lines = ["|순위|기간조회수|평균시청|유지율|순구독|제목|", "|---:|---:|---:|---:|---:|---|"]
    for idx, v in enumerate(videos[:limit], 1):
        a = v["analytics_window"]
        title = v["title"].replace("|", " ")[:70]
        lines.append(
            f"|{idx}|{a['views']}|{a['average_view_duration_seconds']:.1f}s|{a['retention_signal_percentage']:.1f}%|{a['net_subscribers']}|[{title}]({v['url']})|"
        )
    return "\n".join(lines)


def render_markdown_report(report: dict[str, Any]) -> str:
    channel = report["channel"]
    window = report["analysis_window"]
    insights = report["insights"]
    totals = insights["totals"]
    category_lines = ["|카테고리|영상 수|조회수|순구독|", "|---|---:|---:|---:|"]
    for cat, values in sorted(insights["category_summary"].items(), key=lambda kv: kv[1]["views"], reverse=True):
        category_lines.append(f"|{cat}|{values['videos']}|{values['views']}|{values['net_subscribers']}|")
    scope_warnings = insights.get("scope_warnings", [])
    warning_block = "없음" if not scope_warnings else "\n".join(
        f"- {w['title']} ({', '.join(w['categories'])})" for w in scope_warnings
    )
    return f"""# YouTube Shorts 성과 분석 준비 리포트

- 채널: **{channel['title']}** (`{channel['id']}`, `{channel.get('customUrl')}`)
- 분석 기간: `{window['start_date']}` ~ `{window['end_date']}` ({window['days']}일)
- 분석 영상 수: {totals['videos_analyzed']}
- Analytics 행이 있는 영상 수: {totals['videos_with_analytics_rows']}
- 기간 조회수 합계(Analytics 기준): {totals['period_views_from_analytics']}
- 목록 영상 공개 누적 조회수 합계(Data API 기준): {totals['public_lifetime_views_for_listed_videos']}
- 기간 시청 시간 합계: {totals['estimated_minutes_watched']}분
- 기간 순구독자: {totals['net_subscribers']}

## 조회수 상위 영상

{render_video_table(insights['top_by_views'])}

## 유지율 상위 영상

{render_video_table(insights['top_by_retention'])}

## 구독 전환 상위 영상

{render_video_table(insights['top_by_subscribers'])}

## 카테고리별 요약

{chr(10).join(category_lines)}

## 현재 채널 주제 범위 이탈 후보

{warning_block}

## 다음 분석 포인트

1. 조회수 상위와 유지율 상위가 겹치는 주제를 우선 재생산 후보로 본다.
2. 조회수는 높지만 유지율이 낮은 영상은 훅/초반 설명/시각 자료의 기대 불일치를 점검한다.
3. 유지율은 높지만 조회수가 낮은 영상은 제목·첫 프레임·업로드 타이밍 문제를 의심한다.
4. `ai/software`로 분류된 영상은 현재 채널 운영 기준상 제외 후보로 따로 검토한다.
"""
