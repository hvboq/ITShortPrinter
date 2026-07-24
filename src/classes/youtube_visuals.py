import io
import hashlib
import os
import re
import shutil
import subprocess
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


PROMPT_SAFETY_SUFFIX = (
    "세로형 9:16 풀프레임 기술 뉴스 비주얼, 화면 캡처 아님, "
    "유튜브 쇼츠 UI 없음, 틱톡 UI 없음, 릴스 UI 없음, 좋아요 댓글 공유 버튼 없음, "
    "계정명 없음, 하단 캡션 UI 없음, 실제 회사 로고 없음, Apple 로고 없음, "
    "브랜드 워드마크 없음, 이미지 안 텍스트 없음, generic device와 generic chip만 사용"
)

VISUAL_BEAT_TEMPLATES = [
    "핵심 변화가 곧 시작될 것 같은 긴장감 있는 세로형 IT 뉴스 오프닝 비주얼",
    "generic device와 generic chip이 함께 보이는 정교한 기술 뉴스 설명 비주얼",
    "사용자가 새 기능의 체감 변화를 떠올릴 수 있는 미래적인 생활 장면 비주얼",
    "시장 경쟁과 기술 흐름을 추상적인 빛과 회로 패턴으로 보여주는 분석 비주얼",
    "핵심 내용을 정리하는 차분하고 선명한 세로형 IT 뉴스 클로징 비주얼",
]
MIN_ARTICLE_IMAGE_WIDTH = 480
MIN_ARTICLE_IMAGE_HEIGHT = 270
ARTICLE_LEAD_FRAME_SIZE = (1080, 1920)
ARTICLE_LEAD_FOREGROUND_MAX_SIZE = (980, 1120)
RESAMPLE_LANCZOS = getattr(Image, "Resampling", Image).LANCZOS
PLACEHOLDER_PALETTES = [
    {
        "base": (8, 13, 28),
        "ramp": ((34, 30), (36, 20), (82, 45)),
        "accent": (72, 221, 255),
        "accent_2": (255, 210, 67),
        "glow": ((0, 214, 255), (124, 58, 237), (255, 196, 0)),
    },
    {
        "base": (12, 18, 24),
        "ramp": ((26, 34), (70, 24), (62, 42)),
        "accent": (98, 239, 162),
        "accent_2": (255, 214, 102),
        "glow": ((46, 204, 113), (20, 184, 166), (255, 214, 102)),
    },
    {
        "base": (20, 15, 34),
        "ramp": ((54, 26), (34, 20), (92, 34)),
        "accent": (196, 181, 253),
        "accent_2": (255, 159, 122),
        "glow": ((168, 85, 247), (236, 72, 153), (251, 146, 60)),
    },
    {
        "base": (10, 22, 33),
        "ramp": ((22, 44), (64, 28), (86, 30)),
        "accent": (125, 211, 252),
        "accent_2": (250, 204, 21),
        "glow": ((14, 165, 233), (34, 197, 94), (250, 204, 21)),
    },
]
HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")


def persist_image_bytes(image_bytes: bytes, provider_label: str, images: list[str]) -> str:
    """Write generated image bytes as a Shorts-ready PNG and register it."""
    image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")
    os.makedirs(os.path.dirname(image_path), exist_ok=True)

    with Image.open(io.BytesIO(image_bytes)) as image:
        normalized = normalize_shorts_visual_image(image)
        normalized.save(image_path, format="PNG")

    if get_verbose():
        info(f' => Wrote image from {provider_label} to "{image_path}"')

    images.append(image_path)
    return image_path


def _strip_prompt_artifacts(prompt: str) -> str:
    """Remove response wrappers that make image prompts noisy."""
    prompt = str(prompt or "")
    prompt = re.sub(r"```(?:json)?|```", "", prompt, flags=re.IGNORECASE)
    prompt = re.sub(r"^\s*[-*•\d.)]+\s*", "", prompt)
    prompt = re.sub(r"\s+", " ", prompt).strip(" \"'“”‘’[]{}")
    return prompt


def _make_fallback_visual_prompt(subject: str, index: int) -> str:
    beat = VISUAL_BEAT_TEMPLATES[index % len(VISUAL_BEAT_TEMPLATES)]
    subject = re.sub(r"\s+", " ", str(subject or "최신 IT 뉴스")).strip()
    return f"{subject} 주제를 상징하는 {beat}"


def _apply_visual_beat(prompt: str, index: int) -> str:
    """Add a stable scene role so generated image sequences vary by cut."""
    beat = VISUAL_BEAT_TEMPLATES[index % len(VISUAL_BEAT_TEMPLATES)]
    if beat in prompt:
        return prompt
    return f"{prompt}. 이 컷은 {beat} 구도로 구성"


def _append_prompt_safety(prompt: str) -> str:
    if "유튜브 쇼츠 UI 없음" in prompt and "이미지 안 텍스트 없음" in prompt:
        return prompt
    return f"{prompt}. {PROMPT_SAFETY_SUFFIX}"


def _should_prefix_subject(prompt: str, subject: str) -> bool:
    subject = str(subject or "").strip()
    if not subject or subject in prompt:
        return False
    if HANGUL_RE.search(prompt) and not HANGUL_RE.search(subject):
        return False
    return True


def _resize_cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_width, target_height = size
    scale = max(target_width / image.width, target_height / image.height)
    resized = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        RESAMPLE_LANCZOS,
    )
    left = max(0, (resized.width - target_width) // 2)
    top = max(0, (resized.height - target_height) // 2)
    return resized.crop((left, top, left + target_width, top + target_height))


def _resize_contain(image: Image.Image, max_size: tuple[int, int]) -> Image.Image:
    max_width, max_height = max_size
    scale = min(max_width / image.width, max_height / image.height)
    return image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        RESAMPLE_LANCZOS,
    )


def compose_article_lead_visual(image: Image.Image) -> Image.Image:
    """Preserve a news lead image inside a vertical Shorts-safe visual."""
    width, height = ARTICLE_LEAD_FRAME_SIZE
    source = image.convert("RGB")
    background = _resize_cover(source, ARTICLE_LEAD_FRAME_SIZE).filter(
        ImageFilter.GaussianBlur(34)
    )
    overlay = Image.new("RGBA", ARTICLE_LEAD_FRAME_SIZE, (4, 10, 22, 104))
    canvas = Image.alpha_composite(background.convert("RGBA"), overlay)

    foreground = _resize_contain(source, ARTICLE_LEAD_FOREGROUND_MAX_SIZE)
    foreground_rgba = foreground.convert("RGBA")
    x = (width - foreground.width) // 2
    y = int((height - foreground.height) * 0.43)

    shadow = Image.new("RGBA", ARTICLE_LEAD_FRAME_SIZE, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        (x - 24, y - 24, x + foreground.width + 24, y + foreground.height + 24),
        radius=38,
        fill=(0, 0, 0, 125),
    )
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(20)))

    border = Image.new("RGBA", ARTICLE_LEAD_FRAME_SIZE, (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border)
    border_draw.rounded_rectangle(
        (x - 8, y - 8, x + foreground.width + 8, y + foreground.height + 8),
        radius=26,
        fill=(255, 255, 255, 235),
    )
    canvas = Image.alpha_composite(canvas, border)
    canvas.alpha_composite(foreground_rgba, (x, y))

    return canvas.convert("RGB")


def normalize_shorts_visual_image(image: Image.Image) -> Image.Image:
    """Return a 1080x1920 visual without letting off-ratio sources fail QC."""
    source = image.convert("RGB")
    width, height = source.size
    if width <= 0 or height <= 0:
        raise ValueError("Cannot normalize an empty image.")

    source_ratio = width / height
    target_ratio = ARTICLE_LEAD_FRAME_SIZE[0] / ARTICLE_LEAD_FRAME_SIZE[1]
    if abs(source_ratio - target_ratio) <= 0.08:
        return _resize_cover(source, ARTICLE_LEAD_FRAME_SIZE).convert("RGB")
    return compose_article_lead_visual(source)


def _placeholder_seed(prompt: str) -> int:
    digest = hashlib.sha256(str(prompt or "").encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def _placeholder_palette(prompt: str) -> dict:
    seed = _placeholder_seed(prompt)
    return PLACEHOLDER_PALETTES[seed % len(PLACEHOLDER_PALETTES)]


def _mix_rgb(a: tuple[int, int, int], b: tuple[int, int, int], weight: float) -> tuple[int, int, int]:
    weight = max(0.0, min(1.0, float(weight)))
    return tuple(round(a[i] * (1 - weight) + b[i] * weight) for i in range(3))


def placeholder_display_text(prompt: str) -> str:
    """Return viewer-facing text for the local placeholder card."""
    display = _strip_prompt_artifacts(prompt)
    display = display.replace(PROMPT_SAFETY_SUFFIX, "")
    display = re.split(
        r"\.?\s*세로형 9:16 풀프레임 기술 뉴스 비주얼",
        display,
        maxsplit=1,
    )[0]
    display = re.sub(
        r"^(?=[^\uac00-\ud7a3]{8,180}\s+주제를 반영한\s+).*?\s+주제를 반영한\s+",
        "",
        display,
    )
    display = re.sub(r"\.?\s*이 컷은 [^.。]+ 구도로 구성", "", display)
    display = re.sub(
        r"(유튜브 쇼츠 UI|틱톡 UI|릴스 UI|좋아요|댓글|공유 버튼|계정명|하단 캡션 UI|로고|워드마크|이미지 안 텍스트)\s*없음",
        "",
        display,
    )
    display = re.sub(r"\s+", " ", display).strip(" .,")
    if len(display) > 120:
        display = display[:117].rstrip() + "..."
    return display or "오늘의 IT 핵심 변화"


def finalize_image_prompts(
    prompts: list[str],
    target_count: int,
    subject: str = "",
) -> list[str]:
    """Normalize, dedupe, and fill image prompts for a complete visual sequence."""
    target_count = max(1, int(target_count or 1))
    subject = re.sub(r"\s+", " ", str(subject or "최신 IT 뉴스")).strip()

    normalized = []
    seen = set()
    for raw_prompt in prompts or []:
        prompt = _strip_prompt_artifacts(raw_prompt)
        if not prompt:
            continue
        if _should_prefix_subject(prompt, subject):
            prompt = f"{subject} 주제를 반영한 {prompt}"
        key = re.sub(r"\s+", " ", prompt).casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(_apply_visual_beat(prompt, len(normalized)))
        if len(normalized) >= target_count:
            break

    while len(normalized) < target_count:
        normalized.append(_make_fallback_visual_prompt(subject, len(normalized)))

    return [_append_prompt_safety(prompt) for prompt in normalized[:target_count]]


def download_image(image_url: str, images: list[str]) -> str | None:
    """Download an article image and persist it as a local PNG for MoviePy."""
    if not image_url:
        return None

    import requests

    response = requests.get(image_url, timeout=30)
    response.raise_for_status()

    image = Image.open(io.BytesIO(response.content)).convert("RGB")
    if image.width < MIN_ARTICLE_IMAGE_WIDTH or image.height < MIN_ARTICLE_IMAGE_HEIGHT:
        warning(
            "Downloaded article image is too small for a Shorts lead visual; "
            f"skipping it ({image.width}x{image.height})."
        )
        return None

    image = compose_article_lead_visual(image)
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
        "한국어 IT 뉴스 쇼츠용 세로형 대표 이미지, "
        f"핵심 주제: {topic}, "
        "generic device와 기술 뉴스 분위기, 로고 없음, 화면 UI 없음, 이미지 안 텍스트 없음"
    )


def _persist_local_image(source: Path, images: list[str], provider_label: str) -> str:
    """Copy/normalize a generated local image into .mp for MoviePy consumption."""
    dest = Path(ROOT_DIR) / ".mp" / f"hermes-{uuid4()}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        normalized = normalize_shorts_visual_image(image)
        normalized.save(dest, format="PNG")
    images.append(str(dest))
    if get_verbose():
        info(f' => Consumed {provider_label} image "{source}" as "{dest}"')
    return str(dest)


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
    image_path = _persist_local_image(source, images, "queued Hermes")
    try:
        source.unlink()
    except OSError:
        shutil.move(str(source), str(source.with_suffix(source.suffix + ".used")))
    return image_path


def generate_hermes_cli_image(prompt: str, images: list[str]) -> str | None:
    """Generate an image through Hermes CLI/image_gen and persist it for MoviePy.

    This is intentionally opt-in via HERMES_ENABLE_CLI_IMAGE_GENERATION so tests and
    local smoke runs never spawn a nested Hermes agent unexpectedly. Cron wrappers set
    the flag to prevent production uploads from falling back to placeholder art.
    """
    if os.environ.get("HERMES_ENABLE_CLI_IMAGE_GENERATION") != "1":
        return None

    hermes_cmd = os.environ.get("HERMES_CLI", "hermes")
    provider = os.environ.get("HERMES_IMAGE_PROVIDER", "openai-codex")
    model = os.environ.get("HERMES_IMAGE_MODEL", "gpt-5.5")
    timeout = int(os.environ.get("HERMES_IMAGE_TIMEOUT_SECONDS", "600"))
    request = (
        "Generate one vertical 9:16 YouTube Shorts background image for this Korean IT news prompt. "
        "Use the image_generate tool. Do not include logos, readable text, watermarks, or UI. "
        "After generation, output only the local image file path or URL, no extra prose.\n\n"
        f"Prompt: {prompt}"
    )

    try:
        result = subprocess.run(
            [
                hermes_cmd,
                "-z",
                request,
                "-t",
                "image_gen",
                "--provider",
                provider,
                "-m",
                model,
            ],
            cwd=ROOT_DIR,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - fallback path logs and continues
        warning(f"Hermes CLI image generation failed before completion: {type(exc).__name__}: {exc}")
        return None

    output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
    if result.returncode != 0:
        warning(f"Hermes CLI image generation failed with exit={result.returncode}: {output[-1000:]}")
        return None

    for line in reversed(output.splitlines()):
        candidate = line.strip().strip('"').strip("'")
        if not candidate or candidate.startswith("http://") or candidate.startswith("https://"):
            continue
        path = Path(candidate)
        if path.exists() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            return _persist_local_image(path, images, "Hermes CLI generated")

    warning(f"Hermes CLI image generation did not return a local image path: {output[-1000:]}")
    return None


def generate_placeholder_image(prompt: str, images: list[str]) -> str:
    """Generate a visually rich vertical fallback PNG when Gemini is unavailable."""

    def load_font(size: int):
        candidates = [
            os.path.join(get_fonts_dir(), "malgun.ttf"),
            os.path.join(get_fonts_dir(), "malgunbd.ttf"),
            "C:/Windows/Fonts/malgun.ttf",
            "C:/Windows/Fonts/malgunbd.ttf",
            "/mnt/c/Windows/Fonts/malgun.ttf",
            "/mnt/c/Windows/Fonts/malgunbd.ttf",
            os.path.join(get_fonts_dir(), get_font()),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for candidate in candidates:
            try:
                if candidate and os.path.exists(candidate):
                    return ImageFont.truetype(candidate, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def text_width(draw, text: str, font) -> int:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]

    def wrap_by_pixels(draw, text: str, font, max_width: int, max_lines: int) -> str:
        text = re.sub(r"\s+", " ", str(text)).strip()
        words = text.split()
        lines = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if not current or text_width(draw, candidate, font) <= max_width:
                current = candidate
                continue
            lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
        if current and len(lines) < max_lines:
            lines.append(current)
        if lines and len(" ".join(lines)) < len(text):
            lines[-1] = lines[-1].rstrip(" .,") + "..."
        return "\n".join(lines[:max_lines])

    os.makedirs(os.path.join(ROOT_DIR, ".mp"), exist_ok=True)
    width, height = 1080, 1920
    seed = _placeholder_seed(prompt)
    palette = PLACEHOLDER_PALETTES[seed % len(PLACEHOLDER_PALETTES)]
    base_r, base_g, base_b = palette["base"]
    ramp_r, ramp_g, ramp_b = palette["ramp"]
    accent = palette["accent"]
    accent_2 = palette["accent_2"]
    glow_colors = palette["glow"]

    image = Image.new("RGB", (width, height), color=palette["base"])
    pixels = image.load()
    for y in range(height):
        y_ratio = y / height
        for x in range(width):
            x_ratio = x / width
            r = int(base_r + ramp_r[0] * x_ratio + ramp_r[1] * (1 - y_ratio))
            g = int(base_g + ramp_g[0] * (1 - x_ratio) + ramp_g[1] * y_ratio)
            b = int(base_b + ramp_b[0] * y_ratio + ramp_b[1] * x_ratio)
            pixels[x, y] = (r, g, b)

    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    offset = (seed % 180) - 90
    glow_draw.ellipse(
        (-260 + offset, 90, 590 + offset, 960),
        fill=(*glow_colors[0], 72),
    )
    glow_draw.ellipse(
        (520 - offset, 560, 1360 - offset, 1400),
        fill=(*glow_colors[1], 58),
    )
    glow_draw.ellipse((120, 1240, 940, 2070), fill=(*glow_colors[2], 36))
    image = Image.alpha_composite(
        image.convert("RGBA"),
        glow.filter(ImageFilter.GaussianBlur(90)),
    )
    draw = ImageDraw.Draw(image)

    font_badge = load_font(42)
    font_title = load_font(76)
    font_body = load_font(43)
    font_chip = load_font(62)
    font_caption = load_font(48)
    display_prompt = placeholder_display_text(prompt)

    draw.rounded_rectangle((72, 92, 446, 168), radius=34, fill=(255, 210, 45, 255))
    draw.text((106, 108), "IT NEWS", fill=(8, 18, 36, 255), font=font_badge)
    draw.rounded_rectangle(
        (70, 230, 1010, 675),
        radius=46,
        fill=(6, 14, 30, 196),
        outline=(*accent, 220),
        width=5,
    )
    draw.text(
        (118, 280),
        "오늘의 핵심 기술 이슈",
        fill=(255, 235, 90, 255),
        font=font_title,
    )
    draw.multiline_text(
        (120, 405),
        wrap_by_pixels(draw, display_prompt, font_body, max_width=820, max_lines=5),
        fill=(241, 247, 255, 255),
        font=font_body,
        spacing=18,
    )

    draw.rounded_rectangle(
        (180, 760, 900, 1420),
        radius=74,
        fill=(18, 28, 52, 245),
        outline=(*accent, 255),
        width=8,
    )
    device_fill = _mix_rgb((15, 34, 68), accent, 0.12)
    chip_fill = _mix_rgb((5, 11, 24), palette["base"], 0.45)
    draw.rounded_rectangle((226, 826, 854, 1354), radius=42, fill=(*device_fill, 255))
    for i in range(7):
        x = 280 + i * 84
        line_shift = ((seed >> (i % 12)) & 15) - 7
        color = (*accent, 190) if i % 2 == 0 else (*accent_2, 190)
        draw.line((x, 900, x + 80 + line_shift * 2, 1265), fill=color, width=6)
    draw.rounded_rectangle(
        (365, 1002, 715, 1184),
        radius=38,
        fill=(*chip_fill, 245),
        outline=(*accent_2, 255),
        width=6,
    )
    draw.text((438, 1050), "AI", fill=(*accent_2, 255), font=font_chip)

    draw.rounded_rectangle(
        (96, 1510, 984, 1695),
        radius=42,
        fill=(0, 0, 0, 138),
        outline=(255, 255, 255, 90),
        width=3,
    )
    draw.text((150, 1548), "핵심 변화만 빠르게", fill=(245, 248, 255, 255), font=font_caption)
    draw.text((150, 1622), "짧게 정리해드립니다", fill=(*accent, 255), font=load_font(46))

    for i in range(44):
        x = (i * 211 + seed) % width
        y = 190 + ((i * 137 + seed // 7) % 1430)
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
