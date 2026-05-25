import io
import os
import re
import shutil
import textwrap
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config import ROOT_DIR
from config import get_font
from config import get_fonts_dir
from config import get_verbose
from status import info
from status import warning


def persist_image_bytes(image_bytes: bytes, provider_label: str, images: list[str]) -> str:
    """Write generated image bytes to a PNG file and register it."""
    image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")

    with open(image_path, "wb") as image_file:
        image_file.write(image_bytes)

    if get_verbose():
        info(f' => Wrote image from {provider_label} to "{image_path}"')

    images.append(image_path)
    return image_path


def download_image(image_url: str, images: list[str]) -> str | None:
    """Download an article image and persist it as a local PNG for MoviePy."""
    if not image_url:
        return None

    import requests

    response = requests.get(image_url, timeout=30)
    response.raise_for_status()

    image = Image.open(io.BytesIO(response.content)).convert("RGB")
    image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")
    os.makedirs(os.path.dirname(image_path), exist_ok=True)
    image.save(image_path)
    images.append(image_path)

    if get_verbose():
        info(f' => Downloaded article image to "{image_path}"')

    return image_path


def contextual_thumbnail_prompt(topic: str) -> str:
    """Build the deterministic fallback prompt for a news thumbnail."""
    return (
        "세로형 한국어 IT 뉴스 쇼츠 대표 이미지, "
        f"핵심 주제: {topic}, "
        "generic device와 기술 뉴스 분위기, 로고와 화면 UI와 텍스트 없음"
    )


def consume_hermes_queued_image(images: list[str]) -> str | None:
    """Move the next Hermes-generated queued image into .mp for MoviePy consumption."""
    queue_dir = Path(os.environ.get(
        "HERMES_IMAGE_QUEUE_DIR",
        str(Path(ROOT_DIR) / ".mp" / "hermes_images" / "queue"),
    ))
    if not queue_dir.exists():
        return None

    candidates = sorted(
        path for path in queue_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )
    if not candidates:
        return None

    source = candidates[0]
    dest = Path(ROOT_DIR) / ".mp" / f"hermes-{uuid4()}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)

    image = Image.open(source).convert("RGB")
    image.save(dest)
    try:
        source.unlink()
    except OSError:
        shutil.move(str(source), str(source.with_suffix(source.suffix + ".used")))

    images.append(str(dest))
    if get_verbose():
        info(f' => Consumed Hermes-generated image "{source}" as "{dest}"')
    return str(dest)


def generate_placeholder_image(prompt: str, images: list[str]) -> str:
    """Generate a visually rich vertical fallback PNG when Gemini is unavailable."""

    def load_font(size: int):
        try:
            return ImageFont.truetype(os.path.join(get_fonts_dir(), get_font()), size)
        except Exception:
            return ImageFont.load_default()

    def wrap_korean(text: str, width: int = 18, max_lines: int = 6) -> str:
        text = re.sub(r"\s+", " ", str(text)).strip()
        lines = []
        current = ""
        for token in text.split(" "):
            candidate = f"{current} {token}".strip()
            if len(candidate) <= width:
                current = candidate
                continue
            if current:
                lines.extend(
                    textwrap.wrap(current, width=width, break_long_words=True)
                )
            current = token
            if len(lines) >= max_lines:
                break
        if current and len(lines) < max_lines:
            lines.extend(textwrap.wrap(current, width=width, break_long_words=True))
        lines = lines[:max_lines]
        if lines and len(" ".join(lines)) < len(text):
            lines[-1] = lines[-1].rstrip(" .,") + "…"
        return "\n".join(lines)

    os.makedirs(os.path.join(ROOT_DIR, ".mp"), exist_ok=True)
    width, height = 1080, 1920

    image = Image.new("RGB", (width, height), color=(8, 13, 28))
    pixels = image.load()
    for y in range(height):
        y_ratio = y / height
        for x in range(width):
            x_ratio = x / width
            r = int(12 + 35 * x_ratio + 38 * (1 - y_ratio))
            g = int(20 + 42 * (1 - x_ratio) + 18 * y_ratio)
            b = int(45 + 95 * y_ratio + 55 * x_ratio)
            pixels[x, y] = (r, g, b)

    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-250, 90, 620, 960), fill=(0, 214, 255, 80))
    glow_draw.ellipse((520, 520, 1390, 1430), fill=(124, 58, 237, 72))
    glow_draw.ellipse((120, 1200, 930, 2070), fill=(255, 196, 0, 42))
    image = Image.alpha_composite(
        image.convert("RGBA"),
        glow.filter(ImageFilter.GaussianBlur(90)),
    )
    draw = ImageDraw.Draw(image)

    font_badge = load_font(42)
    font_title = load_font(76)
    font_body = load_font(44)
    font_chip = load_font(62)

    draw.rounded_rectangle((72, 92, 446, 168), radius=34, fill=(255, 210, 45, 255))
    draw.text((106, 108), "IT NEWS", fill=(8, 18, 36, 255), font=font_badge)
    draw.rounded_rectangle(
        (70, 230, 1010, 660),
        radius=46,
        fill=(6, 14, 30, 190),
        outline=(71, 221, 255, 220),
        width=5,
    )
    draw.text(
        (118, 280),
        "오늘의 핵심 기술 이슈",
        fill=(255, 235, 90, 255),
        font=font_title,
    )
    draw.multiline_text(
        (120, 390),
        wrap_korean(prompt, width=22, max_lines=5),
        fill=(241, 247, 255, 255),
        font=font_body,
        spacing=18,
    )

    draw.rounded_rectangle(
        (180, 760, 900, 1420),
        radius=74,
        fill=(18, 28, 52, 245),
        outline=(125, 229, 255, 255),
        width=8,
    )
    draw.rounded_rectangle((226, 826, 854, 1354), radius=42, fill=(15, 34, 68, 255))
    for i in range(7):
        x = 280 + i * 84
        color = (72, 221, 255, 190) if i % 2 == 0 else (255, 210, 67, 190)
        draw.line((x, 900, x + 80, 1265), fill=color, width=6)
    draw.rounded_rectangle(
        (365, 1002, 715, 1184),
        radius=38,
        fill=(5, 11, 24, 245),
        outline=(255, 221, 76, 255),
        width=6,
    )
    draw.text((450, 1050), "A18", fill=(255, 234, 95, 255), font=font_chip)

    draw.rounded_rectangle(
        (96, 1510, 984, 1695),
        radius=42,
        fill=(0, 0, 0, 135),
        outline=(255, 255, 255, 90),
        width=3,
    )
    draw.text((150, 1548), "루머인지, 변화 신호인지", fill=(245, 248, 255, 255), font=load_font(54))
    draw.text((150, 1622), "짧게 정리해드립니다", fill=(114, 236, 255, 255), font=load_font(46))

    for i in range(44):
        x = (i * 211) % width
        y = 190 + ((i * 137) % 1430)
        radius = 3 + (i % 5)
        draw.ellipse(
            (x, y, x + radius, y + radius),
            fill=(255, 255, 255, 80 + (i % 3) * 35),
        )

    image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")
    image.convert("RGB").save(image_path)
    images.append(image_path)
    if get_verbose():
        warning(f'Gemini image unavailable; wrote rich fallback visual to "{image_path}"')
    return image_path
