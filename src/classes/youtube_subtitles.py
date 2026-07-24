import math
import re

from PIL import Image, ImageDraw, ImageFont


SUBTITLE_BACKGROUND_FILL = (0, 0, 0, 255)
SUBTITLE_TEXT_FILL = (255, 255, 255, 255)
SUBTITLE_TEXT_STROKE_FILL = (0, 0, 0, 255)
SUBTITLE_FADE_SECONDS = 0.10
TITLE_OVERLAY_FULL_DURATION_THRESHOLD = 7.0
TITLE_OVERLAY_MAX_DURATION_SECONDS = 5.5
TITLE_OVERLAY_FADE_SECONDS = 0.35
PREFERRED_SUBTITLE_MIN_DURATION_SECONDS = 1.05
ABSOLUTE_SUBTITLE_MIN_DURATION_SECONDS = 0.18
MIN_READABLE_SUBTITLE_SECONDS = 0.65

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？…])\s+")
SPOKEN_CHAR_RE = re.compile(r"[가-힣A-Za-z0-9]")
PUNCTUATION_RE = re.compile(r"[.!?。！？…]")
COMMA_PAUSE_RE = re.compile(r"[,，、:;]")

SUBTITLE_TEXT_CORRECTIONS = {
    "랜오버": "레노버",
    "랜 오버": "레노버",
    "랜노버": "레노버",
    "레너버": "레노버",
    "A375G": "A37 5G",
    "A37 5세대": "A37 5G",
    "에이37 5세대": "A37 5G",
    "갤럭시 에이37": "갤럭시 A37",
    "중국형 가격대": "중급형 가격대",
}


def normalize_subtitle_text(text: str) -> str:
    """Apply deterministic brand/term corrections to generated subtitles."""
    corrected = str(text or "")
    for wrong, right in SUBTITLE_TEXT_CORRECTIONS.items():
        corrected = corrected.replace(wrong, right)
    return corrected


def split_script_for_subtitles(text: str, max_chars: int = 34) -> list[str]:
    """Split a Korean narration script into short subtitle chunks."""
    cleaned = re.sub(r"\s+", " ", normalize_subtitle_text(text)).strip()
    if not cleaned:
        return []

    sentences = [sentence.strip() for sentence in SENTENCE_SPLIT_RE.split(cleaned) if sentence.strip()]
    chunks = []
    for sentence in sentences or [cleaned]:
        words = sentence.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = word
            elif len(word) > max_chars and not current:
                for idx in range(0, len(word), max_chars):
                    part = word[idx : idx + max_chars]
                    if len(part) == max_chars:
                        chunks.append(part)
                    else:
                        current = part
            else:
                current = candidate
        if current:
            chunks.append(current)

    return chunks or [cleaned]


def format_srt_timestamp(seconds: float) -> str:
    """Format seconds as an SRT timestamp."""
    total_millis = max(0, int(round(seconds * 1000)))
    hours = total_millis // 3600000
    minutes = (total_millis % 3600000) // 60000
    secs = (total_millis % 60000) // 1000
    millis = total_millis % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def speech_timing_weight(chunk: str) -> float:
    """Estimate relative spoken duration for one subtitle chunk."""
    compact = re.sub(r"\s+", "", str(chunk))
    spoken_chars = SPOKEN_CHAR_RE.findall(compact)
    punctuation_pause = 0.7 * len(PUNCTUATION_RE.findall(chunk))
    comma_pause = 0.35 * len(COMMA_PAUSE_RE.findall(chunk))
    return max(1.0, len(spoken_chars) + punctuation_pause + comma_pause)


def _merge_subtitle_chunks_for_readability(
    chunks: list[str],
    total_duration: float,
) -> list[str]:
    """Merge caption chunks when the video is too short to read them separately."""
    if not chunks:
        return []

    safe_total_duration = max(1.0, float(total_duration or 1.0))
    max_readable_chunks = max(
        1,
        int(math.floor(safe_total_duration / MIN_READABLE_SUBTITLE_SECONDS)),
    )
    if len(chunks) <= max_readable_chunks:
        return chunks

    merged = []
    index = 0
    while index < len(chunks):
        groups_left = max_readable_chunks - len(merged)
        chunks_left = len(chunks) - index
        take = max(1, int(math.ceil(chunks_left / groups_left)))
        merged.append(" ".join(chunks[index : index + take]))
        index += take
    return merged


def subtitle_chunks_for_duration(
    text: str,
    duration_seconds: float,
    max_chars: int = 34,
) -> list[str]:
    """Split narration into caption chunks that can be read at the video pace."""
    chunks = split_script_for_subtitles(text, max_chars=max_chars)
    if not chunks:
        return []
    total_duration = max(1.0, float(duration_seconds or 1.0))
    return _merge_subtitle_chunks_for_readability(chunks, total_duration)


def _subtitle_min_duration(total_duration: float, chunk_count: int) -> float:
    if chunk_count <= 0:
        return 0.0
    average_duration = max(0.001, float(total_duration) / chunk_count)
    adaptive_minimum = max(
        ABSOLUTE_SUBTITLE_MIN_DURATION_SECONDS,
        average_duration * 0.65,
    )
    return min(
        PREFERRED_SUBTITLE_MIN_DURATION_SECONDS,
        adaptive_minimum,
        average_duration * 0.9,
    )


def _allocate_subtitle_durations(weights: list[float], total_duration: float) -> list[float]:
    if not weights:
        return []

    safe_total_duration = max(1.0, float(total_duration or 1.0))
    total_weight = sum(weights) or len(weights)
    raw_durations = [
        safe_total_duration * weight / total_weight
        for weight in weights
    ]
    min_duration = _subtitle_min_duration(safe_total_duration, len(weights))
    durations = [max(min_duration, duration) for duration in raw_durations]

    overflow = sum(durations) - safe_total_duration
    if overflow > 0 and len(durations) > 1:
        flexible = [max(0.0, duration - min_duration) for duration in durations]
        flexible_total = sum(flexible)
        if flexible_total > 0:
            durations = [
                max(min_duration, duration - overflow * flex / flexible_total)
                for duration, flex in zip(durations, flexible)
            ]

    duration_sum = sum(durations)
    if duration_sum > 0:
        scale = safe_total_duration / duration_sum
        durations = [max(0.001, duration * scale) for duration in durations]

    correction = safe_total_duration - sum(durations)
    durations[-1] = max(0.001, durations[-1] + correction)
    return durations


def build_script_srt_content(
    script: str,
    duration_seconds: float,
    max_chars: int = 24,
) -> str:
    """Build deterministic SRT content from a narration script."""
    total_duration = max(1.0, float(duration_seconds or 1.0))
    chunks = subtitle_chunks_for_duration(
        script,
        duration_seconds=total_duration,
        max_chars=max_chars,
    )
    if not chunks:
        raise ValueError("Cannot generate subtitle fallback because script is empty.")

    weights = [speech_timing_weight(chunk) for chunk in chunks]
    durations = _allocate_subtitle_durations(weights, total_duration)

    lines = []
    cursor = 0.0
    for idx, (chunk, duration) in enumerate(zip(chunks, durations), start=1):
        start_seconds = cursor
        end_seconds = (
            total_duration
            if idx == len(chunks)
            else min(total_duration, cursor + duration)
        )
        cursor = end_seconds
        lines.append(str(idx))
        lines.append(
            f"{format_srt_timestamp(start_seconds)} --> {format_srt_timestamp(end_seconds)}"
        )
        lines.append(chunk)
        lines.append("")
    return "\n".join(lines)


def write_script_srt(
    script: str,
    srt_path: str,
    duration_seconds: float,
    max_chars: int = 24,
) -> str:
    """Write deterministic SRT subtitles from a narration script."""
    with open(srt_path, "w", encoding="utf-8") as file:
        file.write(
            build_script_srt_content(
                script,
                duration_seconds=duration_seconds,
                max_chars=max_chars,
            )
        )
    return srt_path


def parse_srt_timestamp(timestamp: str) -> float:
    """Parse an SRT timestamp into seconds."""
    hours, minutes, rest = timestamp.split(":")
    seconds, millis = rest.split(",")
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(millis) / 1000.0
    )


def parse_srt_entries(srt_path: str) -> list[tuple[float, float, str]]:
    """Parse SRT entries into (start, end, text) tuples."""
    with open(srt_path, "r", encoding="utf-8") as file:
        content = file.read().strip()
    entries = []
    for block in re.split(r"\n\s*\n", content):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start_raw, end_raw = [part.strip() for part in lines[1].split("-->", 1)]
        text = normalize_subtitle_text("\n".join(lines[2:]))
        entries.append((parse_srt_timestamp(start_raw), parse_srt_timestamp(end_raw), text))
    return entries


def _text_bbox(draw, text: str, font, stroke_width: int = 0):
    return draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)


def _text_width(draw, text: str, font, stroke_width: int = 0) -> int:
    bbox = _text_bbox(draw, text, font, stroke_width)
    return bbox[2] - bbox[0]


def _wrap_text_by_pixels(draw, text: str, font, max_width: int, stroke_width: int) -> list[str]:
    words = str(text).replace("\n", " ").split()
    if not words:
        return []

    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or _text_width(draw, candidate, font, stroke_width) <= max_width:
            current = candidate
            continue

        lines.append(current)
        current = word
        while _text_width(draw, current, font, stroke_width) > max_width and len(current) > 1:
            split_at = len(current) - 1
            while split_at > 1 and _text_width(draw, current[:split_at], font, stroke_width) > max_width:
                split_at -= 1
            lines.append(current[:split_at])
            current = current[split_at:]

    if current:
        lines.append(current)
    return lines


def _truncate_to_width(draw, text: str, font, max_width: int, stroke_width: int) -> str:
    suffix = "..."
    text = str(text).strip()
    while text and _text_width(draw, text + suffix, font, stroke_width) > max_width:
        text = text[:-1].rstrip()
    return (text + suffix) if text else suffix


def _fit_text_lines(
    draw,
    text: str,
    font_path: str,
    max_width: int,
    max_lines: int,
    initial_size: int,
    min_size: int,
    stroke_width: int,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    for size in range(initial_size, min_size - 1, -2):
        font = ImageFont.truetype(font_path, size)
        lines = _wrap_text_by_pixels(draw, text, font, max_width, stroke_width)
        if len(lines) <= max_lines:
            return font, lines

    font = ImageFont.truetype(font_path, min_size)
    lines = _wrap_text_by_pixels(draw, text, font, max_width, stroke_width)
    if len(lines) > max_lines:
        kept = lines[:max_lines]
        hidden = " ".join(lines[max_lines:])
        kept[-1] = _truncate_to_width(
            draw,
            f"{kept[-1]} {hidden}".strip(),
            font,
            max_width,
            stroke_width,
        )
        lines = kept
    return font, lines


def title_overlay_display_duration(video_duration: float) -> float:
    """Keep the title available for short videos, but declutter longer ones."""
    duration = max(0.1, float(video_duration or 0.1))
    if duration <= TITLE_OVERLAY_FULL_DURATION_THRESHOLD:
        return duration
    return min(duration, TITLE_OVERLAY_MAX_DURATION_SECONDS)


def render_subtitle_image(
    text: str,
    font_path: str,
    width: int = 1080,
    height: int = 360,
):
    """Render one subtitle block as a transparent RGBA image using Pillow."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    stroke_width = 7
    max_text_width = width - 120
    font, lines = _fit_text_lines(
        draw,
        text,
        font_path,
        max_width=max_text_width,
        max_lines=2,
        initial_size=58,
        min_size=42,
        stroke_width=stroke_width,
    )

    line_metrics = [_text_bbox(draw, line, font, stroke_width) for line in lines]
    line_heights = [(bbox[3] - bbox[1]) for bbox in line_metrics]
    line_widths = [(bbox[2] - bbox[0]) for bbox in line_metrics]

    total_text_height = sum(line_heights) + max(0, len(lines) - 1) * 16
    box_width = min(width - 80, max(line_widths or [0]) + 80)
    box_height = total_text_height + 58
    box_x = (width - box_width) // 2
    box_y = height - box_height - 20
    draw.rounded_rectangle(
        (box_x, box_y, box_x + box_width, box_y + box_height),
        radius=28,
        fill=SUBTITLE_BACKGROUND_FILL,
    )

    y = box_y + 28
    for line, line_width, line_height in zip(lines, line_widths, line_heights):
        x = (width - line_width) // 2
        draw.text(
            (x, y),
            line,
            font=font,
            fill=SUBTITLE_TEXT_FILL,
            stroke_width=stroke_width,
            stroke_fill=SUBTITLE_TEXT_STROKE_FILL,
        )
        y += line_height + 16
    return image


def create_subtitle_clips(srt_path: str, font_path: str) -> list:
    """Create MoviePy ImageClips for subtitles without ImageMagick TextClip."""
    import numpy as np
    from moviepy.editor import ImageClip, vfx

    clips = []
    for start, end, text in parse_srt_entries(srt_path):
        duration = max(0.1, end - start)
        image = render_subtitle_image(text, font_path)
        fade_seconds = min(SUBTITLE_FADE_SECONDS, duration / 4)
        clip = (
            ImageClip(np.array(image))
            .set_start(start)
            .set_duration(duration)
            .set_position(("center", 1280))
        )
        if fade_seconds > 0:
            clip = clip.fx(vfx.fadein, fade_seconds).fx(vfx.fadeout, fade_seconds)
        clips.append(clip)
    return clips


def render_title_overlay_image(
    text: str,
    font_path: str,
    width: int = 1080,
    height: int = 292,
):
    """Render a persistent top title banner as a transparent RGBA image."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    badge_font = ImageFont.truetype(font_path, 31)
    stroke_width = 4

    box_x, box_y = 46, 44
    box_w, box_h = width - 92, 196
    draw.rounded_rectangle(
        (box_x, box_y, box_x + box_w, box_y + box_h),
        radius=34,
        fill=(0, 0, 0, 178),
        outline=(255, 230, 70, 230),
        width=3,
    )
    draw.rounded_rectangle(
        (box_x + 28, box_y + 32, box_x + 142, box_y + 78),
        radius=18,
        fill=(255, 224, 52, 245),
    )
    draw.text((box_x + 50, box_y + 38), "뉴스", font=badge_font, fill=(0, 0, 0, 255))

    max_text_width = box_w - 210
    font, lines = _fit_text_lines(
        draw,
        text,
        font_path,
        max_width=max_text_width,
        max_lines=2,
        initial_size=49,
        min_size=34,
        stroke_width=stroke_width,
    )

    line_metrics = [
        _text_bbox(draw, line, font, stroke_width)
        for line in lines[:2]
    ]
    line_heights = [(bbox[3] - bbox[1]) for bbox in line_metrics]
    total_text_height = sum(line_heights) + max(0, len(line_heights) - 1) * 10
    y = box_y + (box_h - total_text_height) // 2 - 2
    for line, bbox, line_h in zip(lines[:2], line_metrics, line_heights):
        draw.text(
            (box_x + 176, y),
            line,
            font=font,
            fill=(255, 255, 255, 255),
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 255),
        )
        y += line_h + 10
    return image


def create_title_overlay_clip(text: str, font_path: str, duration: float):
    """Create an intro title overlay that avoids covering the whole video."""
    import numpy as np
    from moviepy.editor import ImageClip, vfx

    display_duration = title_overlay_display_duration(duration)
    fade_seconds = min(TITLE_OVERLAY_FADE_SECONDS, display_duration / 3)
    image = render_title_overlay_image(text, font_path)
    clip = (
        ImageClip(np.array(image))
        .set_start(0)
        .set_duration(display_duration)
        .set_position(("center", 0))
    )
    if fade_seconds > 0:
        clip = clip.fx(vfx.fadein, fade_seconds).fx(vfx.fadeout, fade_seconds)
    return clip
