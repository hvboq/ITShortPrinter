import re

import numpy as np
from moviepy.editor import ImageClip
from PIL import Image, ImageDraw, ImageFont


def split_script_for_subtitles(text: str, max_chars: int = 34) -> list[str]:
    """Split a Korean narration script into short subtitle chunks."""
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return []

    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.?!。！？])\s+", cleaned)
        if sentence.strip()
    ]
    chunks = []
    for sentence in sentences or [cleaned]:
        words = sentence.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = word
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
    content = open(srt_path, "r", encoding="utf-8").read().strip()
    entries = []
    for block in re.split(r"\n\s*\n", content):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start_raw, end_raw = [part.strip() for part in lines[1].split("-->", 1)]
        text = "\n".join(lines[2:])
        entries.append((parse_srt_timestamp(start_raw), parse_srt_timestamp(end_raw), text))
    return entries


def render_subtitle_image(
    text: str,
    font_path: str,
    width: int = 1080,
    height: int = 360,
):
    """Render one subtitle block as a transparent RGBA image using Pillow."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, 58)
    stroke_width = 7

    raw_words = str(text).replace("\n", " ").split()
    lines = []
    current = ""
    for word in raw_words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font, stroke_width=stroke_width)
        if current and (bbox[2] - bbox[0]) > width - 120:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    lines = lines[:2]

    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    total_text_height = sum(line_heights) + max(0, len(lines) - 1) * 16
    box_width = min(width - 80, max(line_widths or [0]) + 80)
    box_height = total_text_height + 58
    box_x = (width - box_width) // 2
    box_y = height - box_height - 20
    draw.rounded_rectangle(
        (box_x, box_y, box_x + box_width, box_y + box_height),
        radius=28,
        fill=(0, 0, 0, 170),
    )

    y = box_y + 28
    for line, line_width, line_height in zip(lines, line_widths, line_heights):
        x = (width - line_width) // 2
        draw.text(
            (x, y),
            line,
            font=font,
            fill=(255, 245, 80, 255),
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 255),
        )
        y += line_height + 16
    return image


def create_subtitle_clips(srt_path: str, font_path: str) -> list:
    """Create MoviePy ImageClips for subtitles without ImageMagick TextClip."""
    clips = []
    for start, end, text in parse_srt_entries(srt_path):
        duration = max(0.1, end - start)
        image = render_subtitle_image(text, font_path)
        clip = (
            ImageClip(np.array(image))
            .set_start(start)
            .set_duration(duration)
            .set_position(("center", 1280))
        )
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
    font = ImageFont.truetype(font_path, 49)
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
    draw.text((box_x + 48, box_y + 38), "TOPIC", font=badge_font, fill=(0, 0, 0, 255))

    max_text_width = box_w - 210
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font, stroke_width=stroke_width)
        if current and (bbox[2] - bbox[0]) > max_text_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if not lines:
        lines = [text]
    if len(lines) > 2:
        lines = [lines[0], " ".join(lines[1:])]
    if len(lines) > 2:
        lines = lines[:2]

    for idx, line in enumerate(lines[:2]):
        display = line
        while display:
            bbox = draw.textbbox((0, 0), display, font=font, stroke_width=stroke_width)
            if bbox[2] - bbox[0] <= max_text_width or len(display) <= 8:
                break
            display = display[:-2].rstrip() + "…"
        lines[idx] = display

    line_metrics = [
        draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)
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
    """Create a full-duration top title overlay clip."""
    image = render_title_overlay_image(text, font_path)
    return (
        ImageClip(np.array(image))
        .set_start(0)
        .set_duration(max(0.1, float(duration or 0.1)))
        .set_position(("center", 0))
    )
