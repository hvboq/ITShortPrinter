from __future__ import annotations

import hashlib
import shutil
import re
import tempfile
from pathlib import Path
from uuid import uuid4

import numpy as np
from moviepy.editor import VideoFileClip
from PIL import Image, ImageDraw, ImageFont, ImageStat, ImageOps

from .youtube_content import METADATA_TITLE_MAX_CHARS
from .youtube_content import script_char_count, script_quality_warnings, script_sentence_count
from .youtube_subtitles import title_overlay_display_duration

SHORTS_TARGET_SIZE = (1080, 1920)
SHORTS_ASPECT_RATIO = SHORTS_TARGET_SIZE[0] / SHORTS_TARGET_SIZE[1]
MIN_REVIEW_DURATION_SECONDS = 5.0
MIN_TARGET_REVIEW_DURATION_SECONDS = 20.0
MAX_REVIEW_DURATION_SECONDS = 180.0
MIN_REVIEW_FPS = 24.0
MAX_REVIEW_FPS = 60.0
MIN_BYTES_PER_SECOND = 50_000
MIN_AUDIO_PEAK = 0.03
MIN_AUDIO_RMS = 0.006
CLIPPING_AUDIO_PEAK = 0.98
MIN_STRUCTURE_IMAGE_COUNT = 2
MIN_STRUCTURE_IMAGE_PROMPT_COUNT = 2
MIN_STRUCTURE_IMAGE_WIDTH = 720
MIN_STRUCTURE_IMAGE_HEIGHT = 1280
IMAGE_FINGERPRINT_SIZE = (16, 16)
MIN_STRUCTURE_LONG_VIDEO_VISUAL_CLIPS = 3
LONG_VIDEO_STRUCTURE_SECONDS = 15.0
MIN_AVERAGE_SUBTITLE_SECONDS = 0.35
MIN_SUBTITLE_COVERAGE_RATIO = 0.85
MAX_SUBTITLE_START_DELAY_SECONDS = 2.0
MAX_SUBTITLE_END_GAP_SECONDS = 2.5
MIN_CENTER_CONTENT_CONTRAST = 6.0
MIN_RENDERED_SUBTITLE_CONTRAST = 18.0
MIN_RENDERED_SUBTITLE_DARK_RATIO = 0.03
MIN_RENDERED_SUBTITLE_BRIGHT_RATIO = 0.0015
MIN_RENDERED_TITLE_CONTRAST = 14.0
MIN_RENDERED_TITLE_DARK_RATIO = 0.02
MIN_RENDERED_TITLE_BRIGHT_RATIO = 0.001
MIN_FRAME_MOTION_SCORE = 1.0
REVIEW_SHEET_THUMBNAIL_SIZE = (270, 480)
REVIEW_SHEET_LABEL_HEIGHT = 34
REVIEW_SHEET_PADDING = 16
MOTION_ANALYSIS_SIZE = (96, 170)
HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
UUID_LIKE_TITLE_RE = re.compile(
    r"^(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{8}[- ][0-9a-fA-F]{4}[- ][0-9a-fA-F]{4}[- ][0-9a-fA-F]{4}[- ][0-9a-fA-F]{12})(?:\.[A-Za-z0-9]+)?$"
)


def _review_timestamp(duration: float, ratio: float = 0.35) -> float:
    """Pick a frame time that avoids black first/last frames on short clips."""
    if duration <= 0:
        return 0.0
    if duration <= 2:
        return max(0.0, duration / 2)
    return min(max(duration * ratio, 1.0), max(duration - 1.0, 0.0))


def _review_timestamps(duration: float, ratio: float = 0.35) -> list[float]:
    primary = _review_timestamp(duration, ratio=ratio)
    if duration <= 2:
        candidates = [primary]
    elif duration <= 8:
        candidates = [
            primary,
            min(max(duration * 0.75, 1.0), max(duration - 0.5, 0.0)),
        ]
    else:
        intro = min(max(duration * 0.08, 1.0), max(duration - 1.0, 0.0))
        candidates = [
            intro,
            primary,
            min(max(duration * 0.58, 1.0), max(duration - 1.0, 0.0)),
            min(max(duration * 0.82, 1.0), max(duration - 1.0, 0.0)),
        ]

    timestamps: list[float] = []
    for candidate in candidates:
        timestamp = round(float(candidate), 3)
        if not any(abs(timestamp - existing) < 0.25 for existing in timestamps):
            timestamps.append(timestamp)
    return timestamps


def _review_frame_path(frame_path: Path, index: int) -> Path:
    if index == 0:
        return frame_path
    return frame_path.with_name(f"{frame_path.stem}_{index + 1}{frame_path.suffix}")


def _review_sheet_path(frame_path: Path) -> Path:
    return frame_path.with_name(f"{frame_path.stem}_sheet.png")


def _create_review_contact_sheet(
    frame_paths: list[Path],
    timestamps: list[float],
    sheet_path: Path,
) -> Path | None:
    if not frame_paths:
        return None

    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnails = []
    for frame_path in frame_paths:
        with Image.open(frame_path) as image:
            thumbnail = ImageOps.fit(
                image.convert("RGB"),
                REVIEW_SHEET_THUMBNAIL_SIZE,
                method=Image.Resampling.LANCZOS,
            )
            thumbnails.append(thumbnail)

    thumb_width, thumb_height = REVIEW_SHEET_THUMBNAIL_SIZE
    count = len(thumbnails)
    width = REVIEW_SHEET_PADDING * (count + 1) + thumb_width * count
    height = REVIEW_SHEET_PADDING * 2 + REVIEW_SHEET_LABEL_HEIGHT + thumb_height
    sheet = Image.new("RGB", (width, height), (18, 21, 28))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    for index, thumbnail in enumerate(thumbnails):
        x = REVIEW_SHEET_PADDING + index * (thumb_width + REVIEW_SHEET_PADDING)
        label = f"{timestamps[index]:.2f}s" if index < len(timestamps) else f"frame {index + 1}"
        draw.text((x, REVIEW_SHEET_PADDING), label, fill=(245, 248, 255), font=font)
        sheet.paste(thumbnail, (x, REVIEW_SHEET_PADDING + REVIEW_SHEET_LABEL_HEIGHT))

    sheet.save(sheet_path)
    return sheet_path


def _unique_review_warnings(warnings: list[str]) -> list[str]:
    unique: list[str] = []
    for warning in warnings:
        if warning not in unique:
            unique.append(warning)
    return unique


def _quality_pass(review: dict, structure: dict | None = None) -> bool:
    if review.get("review_quality_pass") is not True:
        return False
    if structure is not None and structure.get("structure_quality_pass") is not True:
        return False
    return True


def _metadata_title_quality(metadata: dict | None) -> dict:
    if metadata is None:
        return {
            "metadata_title": "",
            "metadata_title_char_count": 0,
            "metadata_title_has_hangul": False,
            "warnings": [],
        }

    title = ""
    if isinstance(metadata, dict):
        title = str(metadata.get("title") or "")
    title = re.sub(r"\s+", " ", title).strip()
    char_count = len(re.sub(r"\s+", "", title))
    has_hangul = bool(HANGUL_RE.search(title))
    warnings: list[str] = []

    if not title:
        warnings.append("structure_title_missing")
    else:
        if UUID_LIKE_TITLE_RE.match(title):
            warnings.append("structure_title_uuid_like")
        if char_count > METADATA_TITLE_MAX_CHARS:
            warnings.append("structure_title_too_long")
        if char_count < 4:
            warnings.append("structure_title_too_short")
        if not has_hangul:
            warnings.append("structure_title_not_korean")

    return {
        "metadata_title": title,
        "metadata_title_char_count": char_count,
        "metadata_title_has_hangul": has_hangul,
        "warnings": warnings,
    }


def _parse_srt_timestamp_seconds(timestamp: str) -> float | None:
    match = re.match(r"^\s*(\d+):(\d{2}):(\d{2})[,.](\d{1,3})\s*$", str(timestamp or ""))
    if not match:
        return None
    hours, minutes, seconds, millis = match.groups()
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(millis.ljust(3, "0")[:3]) / 1000.0
    )


def _subtitle_artifact_quality(subtitle_path: str | Path | None) -> dict:
    if subtitle_path is None:
        return {
            "subtitle_path": "",
            "subtitle_file_exists": None,
            "subtitle_file_bytes": None,
            "subtitle_entry_count": None,
            "subtitle_first_start_seconds": None,
            "subtitle_last_end_seconds": None,
            "warnings": [],
        }

    path_text = str(subtitle_path or "").strip()
    if not path_text:
        return {
            "subtitle_path": "",
            "subtitle_file_exists": False,
            "subtitle_file_bytes": None,
            "subtitle_entry_count": 0,
            "subtitle_first_start_seconds": None,
            "subtitle_last_end_seconds": None,
            "warnings": ["structure_subtitle_file_missing"],
        }

    path = Path(path_text)
    if not path.exists():
        return {
            "subtitle_path": path_text,
            "subtitle_file_exists": False,
            "subtitle_file_bytes": None,
            "subtitle_entry_count": 0,
            "subtitle_first_start_seconds": None,
            "subtitle_last_end_seconds": None,
            "warnings": ["structure_subtitle_file_missing"],
        }

    try:
        file_bytes = path.stat().st_size
    except OSError:
        file_bytes = None
    warnings: list[str] = []
    if file_bytes is not None and file_bytes <= 0:
        warnings.append("structure_subtitle_file_empty")

    entry_count = 0
    first_start_seconds = None
    last_end_seconds = None
    if file_bytes:
        try:
            content = path.read_text(encoding="utf-8").strip()
            for block in re.split(r"\n\s*\n", content):
                lines = [line.strip() for line in block.splitlines() if line.strip()]
                if len(lines) >= 3 and "-->" in lines[1]:
                    start_raw, end_raw = [part.strip() for part in lines[1].split("-->", 1)]
                    start_seconds = _parse_srt_timestamp_seconds(start_raw)
                    end_seconds = _parse_srt_timestamp_seconds(end_raw)
                    if start_seconds is None or end_seconds is None or end_seconds <= start_seconds:
                        warnings.append("structure_subtitle_timestamp_invalid")
                        continue
                    entry_count += 1
                    first_start_seconds = (
                        start_seconds
                        if first_start_seconds is None
                        else min(first_start_seconds, start_seconds)
                    )
                    last_end_seconds = (
                        end_seconds
                        if last_end_seconds is None
                        else max(last_end_seconds, end_seconds)
                    )
        except Exception:
            warnings.append("structure_subtitle_file_unreadable")

    if file_bytes and entry_count <= 0:
        warnings.append("structure_subtitle_entries_missing")

    return {
        "subtitle_path": path_text,
        "subtitle_file_exists": True,
        "subtitle_file_bytes": file_bytes,
        "subtitle_entry_count": entry_count,
        "subtitle_first_start_seconds": first_start_seconds,
        "subtitle_last_end_seconds": last_end_seconds,
        "warnings": warnings,
    }


def _subtitle_review_entries(subtitle_path: str | Path | None) -> list[tuple[float, float]]:
    path_text = str(subtitle_path or "").strip()
    if not path_text:
        return []
    path = Path(path_text)
    if not path.exists():
        return []

    entries: list[tuple[float, float]] = []
    try:
        content = path.read_text(encoding="utf-8").strip()
    except Exception:
        return []

    for block in re.split(r"\n\s*\n", content):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2 or "-->" not in lines[1]:
            continue
        start_raw, end_raw = [part.strip() for part in lines[1].split("-->", 1)]
        start_seconds = _parse_srt_timestamp_seconds(start_raw)
        end_seconds = _parse_srt_timestamp_seconds(end_raw)
        if start_seconds is None or end_seconds is None or end_seconds <= start_seconds:
            continue
        entries.append((start_seconds, end_seconds))
    return entries


def _subtitle_expected_at(timestamp: float, entries: list[tuple[float, float]]) -> bool:
    return any(start <= timestamp <= end for start, end in entries)


def _title_overlay_expected_at(timestamp: float, duration: float, enabled: bool) -> bool:
    if not enabled or duration <= 0:
        return False
    display_duration = title_overlay_display_duration(duration)
    return 0 <= timestamp <= display_duration


def _image_content_fingerprint(image: Image.Image) -> str:
    """Return a stable low-detail fingerprint for duplicate visual detection."""
    resample = getattr(Image, "Resampling", Image).LANCZOS
    sample = ImageOps.fit(
        image.convert("RGB"),
        IMAGE_FINGERPRINT_SIZE,
        method=resample,
        centering=(0.5, 0.5),
    )
    quantized = bytes(
        channel // 16
        for pixel in sample.getdata()
        for channel in pixel
    )
    return hashlib.sha256(quantized).hexdigest()


def _image_artifact_quality(images: list[str], validate_files: bool = False) -> dict:
    if not validate_files:
        return {
            "image_file_validation_enabled": False,
            "image_file_existing_count": None,
            "image_file_missing_count": None,
            "image_file_unreadable_count": None,
            "image_file_low_resolution_count": None,
            "image_file_bad_aspect_count": None,
            "image_file_duplicate_count": None,
            "image_file_unique_fingerprint_count": None,
            "image_sizes": [],
            "warnings": [],
        }

    existing_count = 0
    missing_count = 0
    unreadable_count = 0
    low_resolution_count = 0
    bad_aspect_count = 0
    image_fingerprints: list[str] = []
    image_sizes: list[list[int]] = []
    warnings: list[str] = []

    for image_path in images:
        path = Path(image_path)
        if not path.exists():
            missing_count += 1
            continue

        existing_count += 1
        try:
            with Image.open(path) as image:
                width, height = image.size
                image_fingerprints.append(_image_content_fingerprint(image))
        except Exception:
            unreadable_count += 1
            continue

        image_sizes.append([int(width), int(height)])
        if width < MIN_STRUCTURE_IMAGE_WIDTH or height < MIN_STRUCTURE_IMAGE_HEIGHT:
            low_resolution_count += 1
        if height <= 0 or abs((width / height) - SHORTS_ASPECT_RATIO) > 0.08:
            bad_aspect_count += 1

    if missing_count > 0:
        warnings.append("structure_image_file_missing")
    if unreadable_count > 0:
        warnings.append("structure_image_file_unreadable")
    if existing_count - unreadable_count < MIN_STRUCTURE_IMAGE_COUNT:
        warnings.append("structure_image_file_count_low")
    if low_resolution_count > 0:
        warnings.append("structure_image_resolution_low")
    if bad_aspect_count > 0:
        warnings.append("structure_image_aspect_ratio_not_9_16")
    duplicate_count = len(image_fingerprints) - len(set(image_fingerprints))
    if duplicate_count > 0:
        warnings.append("structure_image_file_duplicate")

    return {
        "image_file_validation_enabled": True,
        "image_file_existing_count": existing_count,
        "image_file_missing_count": missing_count,
        "image_file_unreadable_count": unreadable_count,
        "image_file_low_resolution_count": low_resolution_count,
        "image_file_bad_aspect_count": bad_aspect_count,
        "image_file_duplicate_count": duplicate_count,
        "image_file_unique_fingerprint_count": len(set(image_fingerprints)),
        "image_sizes": image_sizes,
        "warnings": warnings,
    }


def build_structure_quality_fields(
    *,
    script: str,
    images: list[str],
    image_prompts: list[str] | None,
    duration: float | None,
    metadata: dict | None = None,
    subtitle_path: str | Path | None = None,
    validate_image_files: bool = False,
    subtitle_max_chars: int = 24,
    placeholder_visuals_used: bool = False,
    placeholder_visual_reasons: list[str] | None = None,
) -> dict:
    """Return manifest-friendly quality fields for the generated content structure."""
    from . import youtube_composer, youtube_subtitles

    script = str(script or "").strip()
    images = [str(image) for image in (images or []) if str(image).strip()]
    image_prompts = [str(prompt) for prompt in (image_prompts or []) if str(prompt).strip()]
    placeholder_visual_reasons = [
        re.sub(r"\s+", " ", str(reason or "")).strip()
        for reason in (placeholder_visual_reasons or [])
        if str(reason or "").strip()
    ]
    unique_image_prompt_keys = {
        re.sub(r"\s+", " ", prompt).strip().casefold()
        for prompt in image_prompts
    }
    safe_duration = max(0.0, float(duration or 0.0))
    warnings: list[str] = []

    script_chars = script_char_count(script)
    script_sentences = script_sentence_count(script)
    subtitle_chunks = youtube_subtitles.subtitle_chunks_for_duration(
        script,
        duration_seconds=safe_duration,
        max_chars=subtitle_max_chars,
    )
    subtitle_chunk_count = len(subtitle_chunks)
    average_subtitle_seconds = (
        safe_duration / subtitle_chunk_count
        if safe_duration > 0 and subtitle_chunk_count > 0
        else None
    )
    visual_timeline = youtube_composer._select_visual_paths(images, safe_duration) if images and safe_duration > 0 else []
    visual_clip_count = len(visual_timeline)
    estimated_visual_clip_seconds = (
        round(safe_duration / visual_clip_count, 2)
        if safe_duration > 0 and visual_clip_count > 0
        else None
    )
    title_quality = _metadata_title_quality(metadata)
    subtitle_quality = _subtitle_artifact_quality(subtitle_path)
    image_quality = _image_artifact_quality(images, validate_files=validate_image_files)
    subtitle_first_start = subtitle_quality["subtitle_first_start_seconds"]
    subtitle_last_end = subtitle_quality["subtitle_last_end_seconds"]
    subtitle_coverage_ratio = None
    if safe_duration > 0 and subtitle_first_start is not None and subtitle_last_end is not None:
        covered_start = min(safe_duration, max(0.0, float(subtitle_first_start)))
        covered_end = min(safe_duration, max(0.0, float(subtitle_last_end)))
        subtitle_coverage_ratio = round(
            max(0.0, covered_end - covered_start) / safe_duration,
            3,
        )

    warnings.extend(script_quality_warnings(script))
    warnings.extend(title_quality["warnings"])
    warnings.extend(subtitle_quality["warnings"])
    warnings.extend(image_quality["warnings"])

    if safe_duration <= 0:
        warnings.append("structure_duration_missing")
    elif safe_duration < MIN_TARGET_REVIEW_DURATION_SECONDS:
        warnings.append("structure_duration_too_short")
    if len(images) < MIN_STRUCTURE_IMAGE_COUNT:
        warnings.append("structure_image_count_low")
    if not image_prompts or (
        safe_duration >= LONG_VIDEO_STRUCTURE_SECONDS
        and len(image_prompts) < MIN_STRUCTURE_IMAGE_PROMPT_COUNT
    ):
        warnings.append("structure_image_prompt_count_low")
    if len(unique_image_prompt_keys) < len(image_prompts):
        warnings.append("structure_image_prompt_duplicate")
    if placeholder_visuals_used:
        warnings.append("structure_placeholder_visuals_used")
    if safe_duration >= LONG_VIDEO_STRUCTURE_SECONDS and visual_clip_count < MIN_STRUCTURE_LONG_VIDEO_VISUAL_CLIPS:
        warnings.append("structure_visual_clip_count_low")
    if (
        safe_duration >= LONG_VIDEO_STRUCTURE_SECONDS
        and subtitle_quality["subtitle_file_exists"] is True
        and subtitle_quality["subtitle_entry_count"] is not None
        and subtitle_quality["subtitle_entry_count"] < 2
    ):
        warnings.append("structure_subtitle_entry_count_low")
    if safe_duration >= LONG_VIDEO_STRUCTURE_SECONDS and subtitle_quality["subtitle_file_exists"] is True:
        if subtitle_first_start is not None and subtitle_first_start > MAX_SUBTITLE_START_DELAY_SECONDS:
            warnings.append("structure_subtitle_starts_late")
        if subtitle_last_end is not None and safe_duration - subtitle_last_end > MAX_SUBTITLE_END_GAP_SECONDS:
            warnings.append("structure_subtitle_ends_early")
        if subtitle_coverage_ratio is not None and subtitle_coverage_ratio < MIN_SUBTITLE_COVERAGE_RATIO:
            warnings.append("structure_subtitle_coverage_low")
    if average_subtitle_seconds is not None and average_subtitle_seconds < MIN_AVERAGE_SUBTITLE_SECONDS:
        warnings.append("structure_subtitles_too_dense")

    return {
        "script_char_count": script_chars,
        "script_sentence_count": script_sentences,
        "metadata_title": title_quality["metadata_title"],
        "metadata_title_char_count": title_quality["metadata_title_char_count"],
        "metadata_title_has_hangul": title_quality["metadata_title_has_hangul"],
        "image_count": len(images),
        "image_file_validation_enabled": image_quality["image_file_validation_enabled"],
        "image_file_existing_count": image_quality["image_file_existing_count"],
        "image_file_missing_count": image_quality["image_file_missing_count"],
        "image_file_unreadable_count": image_quality["image_file_unreadable_count"],
        "image_file_low_resolution_count": image_quality["image_file_low_resolution_count"],
        "image_file_bad_aspect_count": image_quality["image_file_bad_aspect_count"],
        "image_file_duplicate_count": image_quality["image_file_duplicate_count"],
        "image_file_unique_fingerprint_count": image_quality["image_file_unique_fingerprint_count"],
        "image_sizes": image_quality["image_sizes"],
        "image_prompt_count": len(image_prompts),
        "image_prompt_unique_count": len(unique_image_prompt_keys),
        "placeholder_visuals_used": bool(placeholder_visuals_used),
        "placeholder_visual_reasons": placeholder_visual_reasons,
        "visual_clip_count": visual_clip_count,
        "estimated_visual_clip_seconds": estimated_visual_clip_seconds,
        "subtitle_path": subtitle_quality["subtitle_path"],
        "subtitle_file_exists": subtitle_quality["subtitle_file_exists"],
        "subtitle_file_bytes": subtitle_quality["subtitle_file_bytes"],
        "subtitle_entry_count": subtitle_quality["subtitle_entry_count"],
        "subtitle_first_start_seconds": (
            round(subtitle_first_start, 3)
            if subtitle_first_start is not None
            else None
        ),
        "subtitle_last_end_seconds": (
            round(subtitle_last_end, 3)
            if subtitle_last_end is not None
            else None
        ),
        "subtitle_coverage_ratio": subtitle_coverage_ratio,
        "subtitle_chunk_count": subtitle_chunk_count,
        "average_subtitle_seconds": (
            round(average_subtitle_seconds, 2)
            if average_subtitle_seconds is not None
            else None
        ),
        "structure_warnings": warnings,
        "structure_quality_pass": not warnings,
    }


def review_archive_status(review: dict, structure: dict | None = None) -> str:
    """Return the archive status that best matches a generated video's QC result."""
    return "generated" if _quality_pass(review, structure) else "needs_review"


def _copy_to_ascii_temp(video_path: Path, temp_dir: Path | None = None) -> Path:
    suffix = video_path.suffix if video_path.suffix and video_path.suffix.isascii() else ".mp4"
    base_dir = temp_dir or Path(tempfile.gettempdir()) / "it-short-video-review"
    base_dir.mkdir(parents=True, exist_ok=True)
    temp_path = base_dir / f"review-{uuid4().hex}{suffix}"
    shutil.copy2(video_path, temp_path)
    return temp_path


def _open_video_clip(video_path: Path, temp_dir: Path | None = None):
    try:
        return VideoFileClip(str(video_path)), None
    except Exception as direct_error:
        temp_path = _copy_to_ascii_temp(video_path, temp_dir=temp_dir)
        try:
            return VideoFileClip(str(temp_path)), temp_path
        except Exception as fallback_error:
            temp_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"Failed to open video for review: {video_path}"
            ) from fallback_error or direct_error


def _analyze_review_frame(
    frame_path: Path,
    subtitle_expected: bool = False,
    title_overlay_expected: bool = False,
) -> dict:
    warnings: list[str] = []
    try:
        with Image.open(frame_path) as image:
            grayscale = image.convert("L")
            stats = ImageStat.Stat(grayscale)
            brightness = round(float(stats.mean[0]), 2)
            contrast = round(float(stats.stddev[0]), 2)
            width, height = grayscale.size
            center_box = (
                int(width * 0.12),
                int(height * 0.22),
                int(width * 0.88),
                int(height * 0.72),
            )
            center_stats = ImageStat.Stat(grayscale.crop(center_box))
            center_brightness = round(float(center_stats.mean[0]), 2)
            center_contrast = round(float(center_stats.stddev[0]), 2)
            title_contrast = None
            title_dark_ratio = None
            title_bright_ratio = None
            if title_overlay_expected:
                title_box = (
                    int(width * 0.04),
                    int(height * 0.02),
                    int(width * 0.96),
                    int(height * 0.16),
                )
                title_region = grayscale.crop(title_box)
                title_stats = ImageStat.Stat(title_region)
                title_contrast = round(float(title_stats.stddev[0]), 2)
                title_pixels = np.asarray(title_region, dtype=np.uint8)
                pixel_count = max(1, int(title_pixels.size))
                title_dark_ratio = round(float(np.count_nonzero(title_pixels < 55) / pixel_count), 4)
                title_bright_ratio = round(float(np.count_nonzero(title_pixels > 210) / pixel_count), 4)
            caption_contrast = None
            caption_dark_ratio = None
            caption_bright_ratio = None
            if subtitle_expected:
                caption_box = (
                    int(width * 0.08),
                    int(height * 0.72),
                    int(width * 0.92),
                    int(height * 0.86),
                )
                caption_region = grayscale.crop(caption_box)
                caption_stats = ImageStat.Stat(caption_region)
                caption_contrast = round(float(caption_stats.stddev[0]), 2)
                caption_pixels = np.asarray(caption_region, dtype=np.uint8)
                pixel_count = max(1, int(caption_pixels.size))
                caption_dark_ratio = round(float(np.count_nonzero(caption_pixels < 45) / pixel_count), 4)
                caption_bright_ratio = round(float(np.count_nonzero(caption_pixels > 210) / pixel_count), 4)
    except Exception:
        return {
            "review_frame_brightness": None,
            "review_frame_contrast": None,
            "review_frame_center_brightness": None,
            "review_frame_center_contrast": None,
            "review_frame_title_overlay_expected": bool(title_overlay_expected),
            "review_frame_title_contrast": None,
            "review_frame_title_dark_ratio": None,
            "review_frame_title_bright_ratio": None,
            "review_frame_subtitle_expected": bool(subtitle_expected),
            "review_frame_caption_contrast": None,
            "review_frame_caption_dark_ratio": None,
            "review_frame_caption_bright_ratio": None,
            "review_warnings": ["review_frame_analysis_failed"],
        }

    if brightness < 12:
        warnings.append("review_frame_very_dark")
    elif brightness > 243:
        warnings.append("review_frame_very_bright")
    if contrast < 2:
        warnings.append("review_frame_low_contrast")
    if center_contrast < MIN_CENTER_CONTENT_CONTRAST:
        warnings.append("review_frame_center_empty")
    if title_overlay_expected and (
        title_contrast is None
        or title_dark_ratio is None
        or title_bright_ratio is None
        or title_contrast < MIN_RENDERED_TITLE_CONTRAST
        or title_dark_ratio < MIN_RENDERED_TITLE_DARK_RATIO
        or title_bright_ratio < MIN_RENDERED_TITLE_BRIGHT_RATIO
    ):
        warnings.append("review_title_region_not_visible")
    if subtitle_expected and (
        caption_contrast is None
        or caption_dark_ratio is None
        or caption_bright_ratio is None
        or caption_contrast < MIN_RENDERED_SUBTITLE_CONTRAST
        or caption_dark_ratio < MIN_RENDERED_SUBTITLE_DARK_RATIO
        or caption_bright_ratio < MIN_RENDERED_SUBTITLE_BRIGHT_RATIO
    ):
        warnings.append("review_subtitle_region_not_visible")

    return {
        "review_frame_brightness": brightness,
        "review_frame_contrast": contrast,
        "review_frame_center_brightness": center_brightness,
        "review_frame_center_contrast": center_contrast,
        "review_frame_title_overlay_expected": bool(title_overlay_expected),
        "review_frame_title_contrast": title_contrast,
        "review_frame_title_dark_ratio": title_dark_ratio,
        "review_frame_title_bright_ratio": title_bright_ratio,
        "review_frame_subtitle_expected": bool(subtitle_expected),
        "review_frame_caption_contrast": caption_contrast,
        "review_frame_caption_dark_ratio": caption_dark_ratio,
        "review_frame_caption_bright_ratio": caption_bright_ratio,
        "review_warnings": warnings,
    }


def _analyze_frame_motion(frame_paths: list[Path]) -> dict:
    """Measure whether sampled review frames actually change over time."""
    if len(frame_paths) < 2:
        return {
            "review_frame_motion_scores": [],
            "review_frame_average_motion_score": None,
            "review_warnings": [],
        }

    try:
        frames = []
        for frame_path in frame_paths:
            with Image.open(frame_path) as image:
                frame = ImageOps.fit(
                    image.convert("L"),
                    MOTION_ANALYSIS_SIZE,
                    method=Image.Resampling.BILINEAR,
                )
                frames.append(np.asarray(frame, dtype=float))
    except Exception:
        return {
            "review_frame_motion_scores": [],
            "review_frame_average_motion_score": None,
            "review_warnings": ["review_frame_motion_analysis_failed"],
        }

    scores = [
        round(float(np.mean(np.abs(current - previous))), 2)
        for previous, current in zip(frames, frames[1:])
    ]
    average_score = round(float(sum(scores) / len(scores)), 2) if scores else None
    warnings = []
    if average_score is not None and average_score < MIN_FRAME_MOTION_SCORE:
        warnings.append("review_frames_low_motion")
    return {
        "review_frame_motion_scores": scores,
        "review_frame_average_motion_score": average_score,
        "review_warnings": warnings,
    }


def _video_file_size(video_path: Path) -> int | None:
    try:
        return video_path.stat().st_size
    except OSError:
        return None


def _video_quality_warnings(
    *,
    duration: float,
    size: list[int] | None,
    fps: float,
    file_size_bytes: int | None,
) -> list[str]:
    warnings: list[str] = []

    if not size or len(size) != 2:
        warnings.append("video_size_missing")
    else:
        width, height = int(size[0]), int(size[1])
        if width <= 0 or height <= 0:
            warnings.append("video_size_invalid")
        else:
            ratio = width / height
            if height <= width:
                warnings.append("video_not_vertical")
            if abs(ratio - SHORTS_ASPECT_RATIO) > 0.03:
                warnings.append("video_aspect_ratio_not_9_16")
            if width < SHORTS_TARGET_SIZE[0] or height < SHORTS_TARGET_SIZE[1]:
                warnings.append("video_resolution_below_1080x1920")

    if duration <= 0:
        warnings.append("video_duration_missing")
    elif duration < MIN_REVIEW_DURATION_SECONDS:
        warnings.append("video_duration_under_5s")
    elif duration < MIN_TARGET_REVIEW_DURATION_SECONDS:
        warnings.append("video_duration_under_target")
    elif duration > MAX_REVIEW_DURATION_SECONDS:
        warnings.append("video_duration_over_180s")

    if fps <= 0:
        warnings.append("video_fps_missing")
    elif fps < MIN_REVIEW_FPS:
        warnings.append("video_fps_below_24")
    elif fps > MAX_REVIEW_FPS:
        warnings.append("video_fps_over_60")

    if file_size_bytes is None:
        warnings.append("video_file_size_missing")
    elif duration >= MIN_REVIEW_DURATION_SECONDS:
        bytes_per_second = file_size_bytes / max(duration, 0.1)
        if bytes_per_second < MIN_BYTES_PER_SECOND:
            warnings.append("video_file_size_low_for_duration")

    return warnings


def _analyze_audio_quality(clip, samples_per_second: int = 60, max_samples: int = 1800) -> dict:
    audio = getattr(clip, "audio", None)
    if audio is None:
        return {
            "review_audio_peak": None,
            "review_audio_rms": None,
            "review_audio_warnings": ["audio_missing"],
        }

    duration = float(getattr(clip, "duration", 0) or 0)
    if duration <= 0:
        return {
            "review_audio_peak": None,
            "review_audio_rms": None,
            "review_audio_warnings": ["audio_duration_missing"],
        }

    try:
        sample_count = min(max(16, int(duration * samples_per_second)), max_samples)
        end_time = max(0.0, duration - 0.001)
        times = np.linspace(0, end_time, sample_count)
        try:
            frames = np.asarray(audio.get_frame(times), dtype=float)
        except Exception:
            frames = np.asarray(
                [audio.get_frame(float(timestamp)) for timestamp in times],
                dtype=float,
            )
    except Exception:
        return {
            "review_audio_peak": None,
            "review_audio_rms": None,
            "review_audio_warnings": ["audio_analysis_failed"],
        }

    if frames.size == 0:
        return {
            "review_audio_peak": 0.0,
            "review_audio_rms": 0.0,
            "review_audio_warnings": ["audio_empty"],
        }

    warnings: list[str] = []
    finite_frames = frames[np.isfinite(frames)]
    if finite_frames.size != frames.size:
        warnings.append("audio_nonfinite_samples")
    if finite_frames.size == 0:
        return {
            "review_audio_peak": 0.0,
            "review_audio_rms": 0.0,
            "review_audio_warnings": warnings,
        }

    peak = float(np.max(np.abs(finite_frames)))
    rms = float(np.sqrt(np.mean(np.square(finite_frames))))
    if peak <= 0 or rms <= 0:
        warnings.append("audio_silent")
    else:
        if peak < MIN_AUDIO_PEAK:
            warnings.append("audio_peak_too_low")
        if rms < MIN_AUDIO_RMS:
            warnings.append("audio_rms_too_low")
        if peak >= CLIPPING_AUDIO_PEAK:
            warnings.append("audio_peak_near_clipping")

    return {
        "review_audio_peak": round(peak, 4),
        "review_audio_rms": round(rms, 4),
        "review_audio_warnings": warnings,
    }


def extract_video_review_frame(
    video_path: str | Path,
    frame_path: str | Path,
    *,
    subtitle_path: str | Path | None = None,
    title_overlay_expected: bool = False,
    ratio: float = 0.35,
    temp_dir: str | Path | None = None,
) -> dict:
    """Extract review frames and return manifest-friendly video metadata."""
    source = Path(video_path)
    frame = Path(frame_path)
    frame.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(temp_dir) if temp_dir is not None else None

    clip = None
    temp_path = None
    try:
        clip, temp_path = _open_video_clip(source, temp_dir=temp_root)
        duration = float(getattr(clip, "duration", 0) or 0)
        fps = float(getattr(clip, "fps", 0) or 0)
        timestamps = _review_timestamps(duration, ratio=ratio)
        subtitle_entries = _subtitle_review_entries(subtitle_path)
        frame_paths = [_review_frame_path(frame, index) for index in range(len(timestamps))]
        frame_qualities = []
        for path, timestamp in zip(frame_paths, timestamps):
            clip.save_frame(str(path), t=timestamp)
            frame_qualities.append(_analyze_review_frame(
                path,
                subtitle_expected=_subtitle_expected_at(timestamp, subtitle_entries),
                title_overlay_expected=_title_overlay_expected_at(
                    timestamp,
                    duration,
                    title_overlay_expected,
                ),
            ))
        try:
            sheet_path = _create_review_contact_sheet(
                frame_paths,
                timestamps,
                _review_sheet_path(frame),
            )
        except Exception:
            sheet_path = None
        primary_frame_quality = frame_qualities[0] if frame_qualities else _analyze_review_frame(frame)
        motion_quality = _analyze_frame_motion(frame_paths)
        audio_quality = _analyze_audio_quality(clip)

        size = getattr(clip, "size", None)
        if size is not None:
            size = list(size)
        file_size_bytes = _video_file_size(source)
        frame_warnings = [
            warning
            for frame_quality in frame_qualities
            for warning in frame_quality["review_warnings"]
        ]
        review_warnings = _unique_review_warnings([
            *frame_warnings,
            *motion_quality["review_warnings"],
            *audio_quality["review_audio_warnings"],
            *_video_quality_warnings(
                duration=duration,
                size=size,
                fps=fps,
                file_size_bytes=file_size_bytes,
            ),
        ])

        return {
            "duration": round(duration, 2),
            "size": size,
            "fps": fps,
            "review_file_size_bytes": file_size_bytes,
            "frame_path": str(frame),
            "review_frame_timestamp": round(timestamps[0], 3) if timestamps else None,
            "review_frame_paths": [str(path) for path in frame_paths],
            "review_frame_timestamps": [round(timestamp, 3) for timestamp in timestamps],
            "review_sheet_path": str(sheet_path) if sheet_path else "",
            "review_sheet_frame_count": len(frame_paths),
            "used_temp_copy": temp_path is not None,
            "review_frame_brightness": primary_frame_quality["review_frame_brightness"],
            "review_frame_contrast": primary_frame_quality["review_frame_contrast"],
            "review_frame_brightness_values": [
                frame_quality["review_frame_brightness"] for frame_quality in frame_qualities
            ],
            "review_frame_contrast_values": [
                frame_quality["review_frame_contrast"] for frame_quality in frame_qualities
            ],
            "review_frame_center_brightness": primary_frame_quality["review_frame_center_brightness"],
            "review_frame_center_contrast": primary_frame_quality["review_frame_center_contrast"],
            "review_frame_center_brightness_values": [
                frame_quality["review_frame_center_brightness"] for frame_quality in frame_qualities
            ],
            "review_frame_center_contrast_values": [
                frame_quality["review_frame_center_contrast"] for frame_quality in frame_qualities
            ],
            "review_title_frame_count": sum(
                1
                for frame_quality in frame_qualities
                if frame_quality["review_frame_title_overlay_expected"]
            ),
            "review_frame_title_contrast": primary_frame_quality["review_frame_title_contrast"],
            "review_frame_title_dark_ratio": primary_frame_quality["review_frame_title_dark_ratio"],
            "review_frame_title_bright_ratio": primary_frame_quality["review_frame_title_bright_ratio"],
            "review_frame_title_contrast_values": [
                frame_quality["review_frame_title_contrast"] for frame_quality in frame_qualities
            ],
            "review_frame_title_dark_ratio_values": [
                frame_quality["review_frame_title_dark_ratio"] for frame_quality in frame_qualities
            ],
            "review_frame_title_bright_ratio_values": [
                frame_quality["review_frame_title_bright_ratio"] for frame_quality in frame_qualities
            ],
            "review_subtitle_frame_count": sum(
                1
                for frame_quality in frame_qualities
                if frame_quality["review_frame_subtitle_expected"]
            ),
            "review_frame_caption_contrast": primary_frame_quality["review_frame_caption_contrast"],
            "review_frame_caption_dark_ratio": primary_frame_quality["review_frame_caption_dark_ratio"],
            "review_frame_caption_bright_ratio": primary_frame_quality["review_frame_caption_bright_ratio"],
            "review_frame_caption_contrast_values": [
                frame_quality["review_frame_caption_contrast"] for frame_quality in frame_qualities
            ],
            "review_frame_caption_dark_ratio_values": [
                frame_quality["review_frame_caption_dark_ratio"] for frame_quality in frame_qualities
            ],
            "review_frame_caption_bright_ratio_values": [
                frame_quality["review_frame_caption_bright_ratio"] for frame_quality in frame_qualities
            ],
            "review_frame_motion_scores": motion_quality["review_frame_motion_scores"],
            "review_frame_average_motion_score": motion_quality["review_frame_average_motion_score"],
            "review_audio_peak": audio_quality["review_audio_peak"],
            "review_audio_rms": audio_quality["review_audio_rms"],
            "review_warnings": review_warnings,
            "review_quality_pass": not review_warnings,
        }
    finally:
        if clip is not None:
            clip.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
