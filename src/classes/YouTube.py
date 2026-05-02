import re
import json
import time
import os
import numpy as np
import assemblyai as aai

from utils import *
from cache import *
from .Tts import TTS
from llm_provider import generate_text
from gemini_image import generate_gemini_image_bytes
from config import *
from status import *
from uuid import uuid4
from constants import *
from news.shorts import build_shorts_script_prompt
from typing import List
from moviepy.editor import *
from termcolor import colored
from selenium import webdriver
from moviepy.video.fx.all import crop
from moviepy.config import change_settings
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from moviepy.video.tools.subtitles import SubtitlesClip
from webdriver_manager.firefox import GeckoDriverManager
from datetime import datetime
from PIL import Image

if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

# Set ImageMagick Path
change_settings({"IMAGEMAGICK_BINARY": get_imagemagick_path()})


class YouTube:
    """
    Class for YouTube Automation.

    Steps to create a YouTube Short:
    1. Generate a topic [DONE]
    2. Generate a script [DONE]
    3. Generate metadata (Title, Description, Tags) [DONE]
    4. Generate AI Image Prompts [DONE]
    4. Generate Images based on generated Prompts [DONE]
    5. Convert Text-to-Speech [DONE]
    6. Show images each for n seconds, n: Duration of TTS / Amount of images [DONE]
    7. Combine Concatenated Images with the Text-to-Speech [DONE]
    """

    def __init__(
        self,
        account_uuid: str,
        account_nickname: str,
        fp_profile_path: str,
        niche: str,
        language: str,
    ) -> None:
        """
        Constructor for YouTube Class.

        Args:
            account_uuid (str): The unique identifier for the YouTube account.
            account_nickname (str): The nickname for the YouTube account.
            fp_profile_path (str): Path to the firefox profile that is logged into the specificed YouTube Account.
            niche (str): The niche of the provided YouTube Channel.
            language (str): The language of the Automation.

        Returns:
            None
        """
        self._account_uuid: str = account_uuid
        self._account_nickname: str = account_nickname
        self._fp_profile_path: str = fp_profile_path
        self._niche: str = niche
        self._language: str = language

        self.images = []
        self.news_article = None

        # Initialize the Firefox profile
        self.options: Options = Options()

        # Set headless state of browser
        if get_headless():
            self.options.add_argument("--headless")

        if not os.path.isdir(self._fp_profile_path):
            raise ValueError(
                f"Firefox profile path does not exist or is not a directory: {self._fp_profile_path}"
            )

        firefox_binary = "/opt/firefox-latest/firefox"
        if os.path.exists(firefox_binary):
            self.options.binary_location = firefox_binary

        self.options.add_argument("-profile")
        self.options.add_argument(self._fp_profile_path)
        self.options.add_argument("--width=1280")
        self.options.add_argument("--height=900")
        self.options.set_preference("app.update.enabled", False)
        self.options.set_preference("browser.shell.checkDefaultBrowser", False)
        self.options.set_preference("browser.startup.homepage_override.mstone", "ignore")

        # Set the service
        geckodriver_path = "/usr/local/bin/geckodriver"
        if os.path.exists(geckodriver_path):
            self.service: Service = Service(geckodriver_path)
        else:
            self.service: Service = Service(GeckoDriverManager().install())

        # Initialize the browser
        self.browser: webdriver.Firefox = webdriver.Firefox(
            service=self.service, options=self.options
        )

    @classmethod
    def for_local_generation(cls, niche: str = "IT News", language: str = "Korean"):
        """Create a YouTube instance for local MP4 generation without launching Firefox."""
        instance = cls.__new__(cls)
        instance._account_uuid = "local-no-upload"
        instance._account_nickname = "local-no-upload"
        instance._fp_profile_path = ""
        instance._niche = niche
        instance._language = language
        instance.images = []
        instance.news_article = None
        instance.browser = None
        instance.service = None
        instance.options = None
        return instance

    @property
    def niche(self) -> str:
        """
        Getter Method for the niche.

        Returns:
            niche (str): The niche
        """
        return self._niche

    @property
    def language(self) -> str:
        """
        Getter Method for the language to use.

        Returns:
            language (str): The language
        """
        return self._language

    def generate_response(self, prompt: str, model_name: str = None) -> str:
        """
        Generates an LLM Response based on a prompt and the user-provided model.

        Args:
            prompt (str): The prompt to use in the text generation.

        Returns:
            response (str): The generated AI Repsonse.
        """
        return generate_text(prompt, model_name=model_name or get_ollama_model())

    def generate_topic(self) -> str:
        """
        Generates a topic based on the YouTube Channel niche.

        Returns:
            topic (str): The generated topic.
        """
        if self.news_article:
            completion = self.news_article.get("title", "").strip()
        else:
            completion = self.generate_response(
                f"Please generate a specific video idea that takes about the following topic: {self.niche}. Make it exactly one sentence. Only return the topic, nothing else."
            )

        if not completion:
            error("Failed to generate Topic.")

        self.subject = completion

        return completion

    def _clean_generated_korean_text(self, text: str) -> str:
        """Clean common LLM artifacts before TTS/subtitles/metadata are rendered."""
        text = str(text or "")
        replacements = {
            "맥그네틱": "마그네틱",
            "AIagentic": "AI",
            "AI Agentic": "에이전틱 AI",
            "agentic AIagentic": "에이전틱 AI",
            "Agentic AIagentic": "에이전틱 AI",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        # Remove stray Hangul jamo/combining fragments such as ᄆᄆ that sometimes appear in titles.
        text = re.sub(r"[\u1100-\u11ff]+", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _clean_metadata_title(self, title: str) -> str:
        """Normalize title text used for upload metadata and the persistent top overlay."""
        title = self._clean_generated_korean_text(title)
        title = re.sub(r"^[\"'“”‘’]+|[\"'“”‘’]+$", "", title).strip()
        ad_replacements = {
            "국내 최초!": "",
            "국내 최초": "",
            "역대급": "큰",
            "수요 폭발": "수요 증가",
            "폭발": "증가",
            "극대화하는 법": "높이는 전략",
            "극대화": "향상",
            "새로운 기준": "새 접근",
        }
        for old, new in ad_replacements.items():
            title = title.replace(old, new)
        title = re.sub(r"\s+([!?])", r"\1", title)
        # Keep Shorts metadata concise; hashtags are allowed for upload but not required in overlay.
        if len(title) > 92:
            title = title[:91].rstrip() + "…"
        return title or "오늘의 IT 핵심 이슈"

    def generate_script(self) -> str:
        """
        Generate a script for a video, depending on the subject of the video, the number of paragraphs, and the AI model.

        Returns:
            script (str): The script of the video.
        """
        sentence_length = get_script_sentence_length()
        if self.news_article:
            prompt = build_shorts_script_prompt(
                self.news_article,
                language=self.language,
                sentence_length=sentence_length,
            )
        else:
            prompt = f"""
        {sentence_length}문장 이내의 한국어 유튜브 쇼츠 대본을 작성해.

        대본은 실제로 읽을 수 있는 짧은 문장들로만 구성해.
        예시 형식:
        "이것은 예시 문장입니다."

        절대 이 프롬프트를 언급하지 마.
        "안녕하세요", "오늘 영상에 오신 걸 환영합니다" 같은 불필요한 도입 없이 바로 핵심으로 들어가.
        대본은 반드시 주제와 직접 관련되어야 한다.
        
        반드시 {sentence_length}문장 제한을 지켜. 각 문장은 짧게 작성해.
        반드시 한국어로만 작성해. 영어 제목/소재가 들어오더라도 자연스러운 한국어로 번역·재구성해.
        마크다운, 제목, 서식, VOICEOVER, NARRATOR 같은 라벨을 절대 쓰지 마.
        대본 자체나 문장 수에 대해 말하지 말고, 실제 나레이션 원문만 반환해.
        
        주제: {self.subject}
        출력 언어: 한국어
        """
        completion = self.generate_response(prompt)

        # Apply regex to remove * and clean common LLM artifacts before TTS/subtitles.
        completion = self._clean_generated_korean_text(re.sub(r"\*", "", completion))

        if not completion:
            error("The generated script is empty.")
            return

        if len(completion) > 5000:
            if get_verbose():
                warning("Generated Script is too long. Retrying...")
            return self.generate_script()

        self.script = completion

        return completion

    def generate_metadata(self) -> dict:
        """
        Generates Video metadata for the to-be-uploaded YouTube Short (Title, Description).

        Returns:
            metadata (dict): The generated metadata.
        """
        title = self._clean_metadata_title(self.generate_response(
            f"다음 주제에 맞는 유튜브 쇼츠 제목을 반드시 한국어 중심으로 작성해. 제품명과 브랜드명은 뉴스 이해에 꼭 필요할 때만 최소한으로 유지하고, 공식 광고처럼 보이는 과장 표현(국내 최초!, 역대급, 폭발, 극대화하는 법, 새로운 기준)은 피해서 중립적인 뉴스 제목으로 써. 해시태그는 최대 2개만 포함하고 전체 92자 미만으로 제한해. 깨진 문자, 한글 자모만 남은 글자, 이모지, 따옴표를 쓰지 마. 제목만 반환해. 주제: {self.subject}"
        ))

        if len(title) > 100:
            if get_verbose():
                warning("Generated Title is too long. Retrying...")
            return self.generate_metadata()

        description = self._clean_generated_korean_text(self.generate_response(
            f"다음 쇼츠 대본을 바탕으로 유튜브 영상 설명을 반드시 한국어 중심으로 작성해. 제품명과 브랜드명은 뉴스 이해에 필요한 경우만 최소한으로 유지해. 구독 유도는 허용하지만 저장 유도는 하지 마. 공식 광고처럼 보이는 과장 표현, 마크다운 굵게 표시, 목록 기호, 영어 섹션 제목은 쓰지 말고 자연스러운 한국어 설명문만 반환해. 대본: {self.script}"
        ))

        self.metadata = {"title": title, "description": description}

        return self.metadata

    def generate_prompts(self) -> List[str]:
        """
        Generates AI Image Prompts based on the provided Video Script.

        Returns:
            image_prompts (List[str]): Generated List of image prompts.
        """
        n_prompts = get_max_image_prompts()

        prompt = f"""
        AI 이미지 생성을 위한 이미지 프롬프트를 정확히 {n_prompts}개 작성해.
        모든 출력은 반드시 한국어로만 작성해.
        주제: {self.subject}

        출력 형식은 문자열만 담긴 JSON 배열이어야 한다.
        JSON 배열 안의 문자열도 한국어로 작성한다.

        각 이미지 프롬프트는 한 문장으로 작성하고,
        영상의 핵심 주제를 반드시 포함한다.

        감정적인 형용사와 구체적인 시각 묘사를 사용해서
        세로형 유튜브 쇼츠 이미지에 어울리게 만든다.

        중요 금지 조건:
        - 이미지 안에 유튜브 쇼츠 UI, 틱톡/릴스 UI, 좋아요/댓글/공유 버튼, 계정명, 하단 캡션 UI를 절대 넣지 않는다.
        - 스마트폰 화면 캡처처럼 보이게 만들지 않는다. 완전한 배경/일러스트/제품 비주얼만 만든다.
        - 실제 회사 로고, Apple 로고, 공식 브랜드 워드마크, 앱 아이콘, 상표 텍스트를 넣지 않는다.
        - 이미지 안에는 글자, 자막, 홍보 문구, UI 텍스트를 넣지 않는다.
        - 뉴스 주제가 실제 브랜드여도 시각 요소는 generic device, generic chip, generic technology scene으로 표현한다.

        반드시 JSON 배열만 반환해.
        다른 설명, 마크다운, 대본 원문은 절대 반환하지 마.

        예시:
        ["미래적인 스마트폰이 어두운 배경에서 빛나는 한국어 IT 뉴스 쇼츠 이미지", "AI 칩셋의 성능 변화를 직관적으로 보여주는 세로형 기술 뉴스 이미지"]

        참고 대본:
        {self.script}
        """

        completion = (
            str(self.generate_response(prompt))
            .replace("```json", "")
            .replace("```", "")
        )

        image_prompts = []

        if "image_prompts" in completion:
            image_prompts = json.loads(completion)["image_prompts"]
        else:
            try:
                image_prompts = json.loads(completion)
                if get_verbose():
                    info(f" => Generated Image Prompts: {image_prompts}")
            except Exception:
                if get_verbose():
                    warning(
                        "LLM returned an unformatted response. Attempting to clean..."
                    )

                # Get everything between [ and ], and turn it into a list
                r = re.compile(r"\[.*\]")
                image_prompts = r.findall(completion)
                if len(image_prompts) == 0:
                    if get_verbose():
                        warning("Failed to generate Image Prompts. Retrying...")
                    return self.generate_prompts()

        if len(image_prompts) > n_prompts:
            image_prompts = image_prompts[:n_prompts]

        safety_suffix = (
            " 세로형 9:16 풀프레임 기술 뉴스 비주얼, 화면 캡처 아님, "
            "유튜브 쇼츠 UI 없음, 틱톡 UI 없음, 릴스 UI 없음, 좋아요 댓글 공유 버튼 없음, "
            "계정명 없음, 하단 캡션 UI 없음, 실제 회사 로고 없음, Apple 로고 없음, "
            "브랜드 워드마크 없음, 이미지 안 텍스트 없음, generic device와 generic chip만 사용"
        )
        image_prompts = [
            prompt if "유튜브 쇼츠 UI 없음" in prompt else f"{prompt}.{safety_suffix}"
            for prompt in image_prompts
        ]

        self.image_prompts = image_prompts

        success(f"Generated {len(image_prompts)} Image Prompts.")

        return image_prompts

    def _persist_image(self, image_bytes: bytes, provider_label: str) -> str:
        """
        Writes generated image bytes to a PNG file in .mp.

        Args:
            image_bytes (bytes): Image payload
            provider_label (str): Label for logging

        Returns:
            path (str): Absolute image path
        """
        image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")

        with open(image_path, "wb") as image_file:
            image_file.write(image_bytes)

        if get_verbose():
            info(f' => Wrote image from {provider_label} to "{image_path}"')

        self.images.append(image_path)
        return image_path

    def generate_placeholder_image(self, prompt: str) -> str:
        """Generate a visually rich vertical fallback PNG when Gemini is rate-limited."""
        from PIL import ImageDraw, ImageFilter, ImageFont
        import textwrap

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
                    lines.extend(textwrap.wrap(current, width=width, break_long_words=True))
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

        # Layered blue/purple gradient so fallback frames never look empty/black.
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
        image = Image.alpha_composite(image.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(90)))
        draw = ImageDraw.Draw(image)

        font_badge = load_font(42)
        font_title = load_font(76)
        font_body = load_font(44)
        font_chip = load_font(62)

        # News badge and headline card.
        draw.rounded_rectangle((72, 92, 446, 168), radius=34, fill=(255, 210, 45, 255))
        draw.text((106, 108), "IT NEWS", fill=(8, 18, 36, 255), font=font_badge)
        draw.rounded_rectangle((70, 230, 1010, 660), radius=46, fill=(6, 14, 30, 190), outline=(71, 221, 255, 220), width=5)
        draw.text((118, 280), "오늘의 핵심 기술 이슈", fill=(255, 235, 90, 255), font=font_title)
        draw.multiline_text((120, 390), wrap_korean(prompt, width=22, max_lines=5), fill=(241, 247, 255, 255), font=font_body, spacing=18)

        # Large abstract device illustration.
        draw.rounded_rectangle((180, 760, 900, 1420), radius=74, fill=(18, 28, 52, 245), outline=(125, 229, 255, 255), width=8)
        draw.rounded_rectangle((226, 826, 854, 1354), radius=42, fill=(15, 34, 68, 255))
        for i in range(7):
            x = 280 + i * 84
            color = (72, 221, 255, 190) if i % 2 == 0 else (255, 210, 67, 190)
            draw.line((x, 900, x + 80, 1265), fill=color, width=6)
        draw.rounded_rectangle((365, 1002, 715, 1184), radius=38, fill=(5, 11, 24, 245), outline=(255, 221, 76, 255), width=6)
        draw.text((450, 1050), "A18", fill=(255, 234, 95, 255), font=font_chip)

        # Bottom visual CTA strip, deliberately separate from generated subtitles.
        draw.rounded_rectangle((96, 1510, 984, 1695), radius=42, fill=(0, 0, 0, 135), outline=(255, 255, 255, 90), width=3)
        draw.text((150, 1548), "루머인지, 변화 신호인지", fill=(245, 248, 255, 255), font=load_font(54))
        draw.text((150, 1622), "짧게 정리해드립니다", fill=(114, 236, 255, 255), font=load_font(46))

        # Subtle particles for movement-friendly detail.
        for i in range(44):
            x = (i * 211) % width
            y = 190 + ((i * 137) % 1430)
            radius = 3 + (i % 5)
            draw.ellipse((x, y, x + radius, y + radius), fill=(255, 255, 255, 80 + (i % 3) * 35))

        image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")
        image.convert("RGB").save(image_path)
        self.images.append(image_path)
        if get_verbose():
            warning(f'Gemini image unavailable; wrote rich fallback visual to "{image_path}"')
        return image_path

    def generate_image_nanobanana2(self, prompt: str) -> str:
        """
        Generates an AI Image using Nano Banana 2 API (Gemini image API).

        Args:
            prompt (str): Prompt for image generation

        Returns:
            path (str): The path to the generated image.
        """
        print(f"Generating Image using Nano Banana 2 API: {prompt}")

        api_key = get_nanobanana2_api_key()
        if not api_key:
            error("nanobanana2_api_key is not configured.")
            return None

        base_url = get_nanobanana2_api_base_url().rstrip("/")
        model = get_nanobanana2_model()
        aspect_ratio = get_nanobanana2_aspect_ratio()

        try:
            image_bytes = generate_gemini_image_bytes(
                prompt=prompt,
                api_key=api_key,
                base_url=base_url,
                model=model,
                aspect_ratio=aspect_ratio,
                timeout=300,
            )
            if image_bytes:
                return self._persist_image(image_bytes, "Nano Banana 2 API")

            if get_verbose():
                warning("Nano Banana 2 did not return an image payload.")
            return None
        except Exception as e:
            if get_verbose():
                warning(f"Failed to generate image with Nano Banana 2 API: {str(e)}")
            return None

    def generate_image(self, prompt: str) -> str:
        """
        Generates an AI Image based on the given prompt using Nano Banana 2.

        Args:
            prompt (str): Reference for image generation

        Returns:
            path (str): The path to the generated image.
        """
        provider = get_image_provider()
        if provider == "placeholder":
            warning("Using placeholder image provider for local smoke testing. Do not use for production uploads.")
            return self.generate_placeholder_image(prompt)
        if provider != "gemini":
            warning(f"Unknown image_provider '{provider}'. Falling back to Gemini.")

        image_path = self.generate_image_nanobanana2(prompt)
        if image_path:
            return image_path

        warning("Gemini image generation failed or was rate-limited. Falling back to placeholder image so video generation can continue.")
        return self.generate_placeholder_image(prompt)

    def generate_script_to_speech(self, tts_instance: TTS) -> str:
        """
        Converts the generated script into Speech using KittenTTS and returns the path to the wav file.

        Args:
            tts_instance (tts): Instance of TTS Class.

        Returns:
            path_to_wav (str): Path to generated audio (WAV Format).
        """
        path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".wav")

        # Clean script, remove every character that is not a word character, a space, a period, a question mark, or an exclamation mark.
        self.script = re.sub(r"[^\w\s.?!]", "", self.script)

        tts_instance.synthesize(self.script, path)

        self.tts_path = path

        if get_verbose():
            info(f' => Wrote TTS to "{path}"')

        return path

    def add_video(self, video: dict) -> None:
        """
        Adds a video to the cache.

        Args:
            video (dict): The video to add

        Returns:
            None
        """
        videos = self.get_videos()
        videos.append(video)

        cache = get_youtube_cache_path()

        with open(cache, "r") as file:
            previous_json = json.loads(file.read())

            # Find our account
            accounts = previous_json["accounts"]
            for account in accounts:
                if account["id"] == self._account_uuid:
                    account["videos"].append(video)

            # Commit changes
            with open(cache, "w") as f:
                f.write(json.dumps(previous_json))

    def _split_script_for_subtitles(self, text: str, max_chars: int = 34) -> List[str]:
        """Split a Korean narration script into short subtitle chunks."""
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        if not cleaned:
            return []

        sentences = [s.strip() for s in re.split(r"(?<=[.?!。！？])\s+", cleaned) if s.strip()]
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

    def generate_subtitles_from_script(self, duration_seconds: float, max_chars: int = 24) -> str:
        """Generate deterministic Korean SRT subtitles from the already-generated script.

        When STT is unavailable, align fallback subtitles by estimated spoken length
        instead of giving every caption the same duration. Korean narration timing is
        much closer when each chunk's duration is proportional to text length, with
        small pauses for punctuation.
        """
        chunks = self._split_script_for_subtitles(getattr(self, "script", ""), max_chars=max_chars)
        if not chunks:
            raise ValueError("Cannot generate subtitle fallback because script is empty.")

        total_duration = max(1.0, float(duration_seconds or 1.0))

        def speech_weight(chunk: str) -> float:
            compact = re.sub(r"\s+", "", str(chunk))
            korean_or_alnum = re.findall(r"[가-힣A-Za-z0-9]", compact)
            punctuation_pause = 0.7 * len(re.findall(r"[.?!。！？]", chunk))
            comma_pause = 0.35 * len(re.findall(r"[,，、;:：]", chunk))
            return max(1.0, len(korean_or_alnum) + punctuation_pause + comma_pause)

        weights = [speech_weight(chunk) for chunk in chunks]
        total_weight = sum(weights) or len(chunks)
        raw_durations = [total_duration * weight / total_weight for weight in weights]

        # Avoid unreadably fast flashes while preserving total duration.
        min_duration = 1.05
        durations = [max(min_duration, duration) for duration in raw_durations]
        overflow = sum(durations) - total_duration
        if overflow > 0 and len(durations) > 1:
            flexible = [max(0.0, duration - min_duration) for duration in durations]
            flexible_total = sum(flexible)
            if flexible_total > 0:
                durations = [
                    duration - overflow * flex / flexible_total
                    for duration, flex in zip(durations, flexible)
                ]

        lines = []
        cursor = 0.0
        for idx, (chunk, duration) in enumerate(zip(chunks, durations), start=1):
            start_seconds = cursor
            end_seconds = total_duration if idx == len(chunks) else min(total_duration, cursor + duration)
            cursor = end_seconds
            lines.append(str(idx))
            lines.append(f"{self._format_srt_timestamp(start_seconds)} --> {self._format_srt_timestamp(end_seconds)}")
            lines.append(chunk)
            lines.append("")

        srt_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".srt")
        with open(srt_path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines))
        if get_verbose():
            info(f' => Wrote script-timed subtitles to "{srt_path}"')
        return srt_path

    def generate_safe_subtitles(self, audio_path: str, duration_seconds: float) -> str:
        """Generate STT subtitles, falling back to script-based subtitles when STT is unavailable."""
        try:
            return self.generate_subtitles(audio_path)
        except Exception as e:
            warning(f"STT subtitle generation failed, falling back to script subtitles: {e}")
            return self.generate_subtitles_from_script(duration_seconds=duration_seconds)

    def _parse_srt_timestamp(self, timestamp: str) -> float:
        """Parse an SRT timestamp into seconds."""
        hours, minutes, rest = timestamp.split(":")
        seconds, millis = rest.split(",")
        return (
            int(hours) * 3600
            + int(minutes) * 60
            + int(seconds)
            + int(millis) / 1000.0
        )

    def _parse_srt_entries(self, srt_path: str) -> list:
        """Parse SRT entries into (start, end, text) tuples."""
        content = open(srt_path, "r", encoding="utf-8").read().strip()
        entries = []
        for block in re.split(r"\n\s*\n", content):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if len(lines) < 3 or "-->" not in lines[1]:
                continue
            start_raw, end_raw = [part.strip() for part in lines[1].split("-->", 1)]
            text = "\n".join(lines[2:])
            entries.append((self._parse_srt_timestamp(start_raw), self._parse_srt_timestamp(end_raw), text))
        return entries

    def _subtitle_font_path(self) -> str:
        """Pick the subtitle font, preferring Malgun Gothic when available.

        The user's requested subtitle font is 맑은 고딕 (Malgun Gothic). In this
        Docker/WSL runtime the Windows font directory may not be mounted, so keep
        Malgun Gothic as the first choice and fall back to bundled Korean-capable
        fonts only when the actual file is unavailable.
        """
        candidates = [
            os.path.join(get_fonts_dir(), "malgun.ttf"),
            os.path.join(get_fonts_dir(), "malgunbd.ttf"),
            "/mnt/c/Windows/Fonts/malgun.ttf",
            "/mnt/c/Windows/Fonts/malgunbd.ttf",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/opentype/unifont/unifont.otf",
            os.path.join(get_fonts_dir(), get_font()),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                if "malgun" not in os.path.basename(candidate).lower() and get_verbose():
                    warning("Malgun Gothic font file was not found; using the best available Korean subtitle font fallback.")
                return candidate
        return candidates[-1]

    def _render_subtitle_image(self, text: str, width: int = 1080, height: int = 360):
        """Render one subtitle block as a transparent RGBA image using Pillow."""
        from PIL import ImageDraw, ImageFont

        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(self._subtitle_font_path(), 58)
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

    def _create_subtitle_clips(self, srt_path: str) -> list:
        """Create MoviePy ImageClips for subtitles without using ImageMagick TextClip."""
        clips = []
        for start, end, text in self._parse_srt_entries(srt_path):
            duration = max(0.1, end - start)
            image = self._render_subtitle_image(text)
            clip = (
                ImageClip(np.array(image))
                .set_start(start)
                .set_duration(duration)
                .set_position(("center", 1280))
            )
            clips.append(clip)
        return clips

    def _overlay_title_text(self) -> str:
        """Return a concise Korean topic title for the persistent top overlay."""
        title = ""
        metadata = getattr(self, "metadata", {}) or {}
        if isinstance(metadata, dict):
            title = str(metadata.get("title") or "")
        if not title:
            title = str(getattr(self, "subject", "") or "")
        # Remove hashtags and over-enthusiastic metadata clutter; keep the core topic.
        title = self._clean_metadata_title(title)
        title = re.sub(r"#[^\s#]+", "", title)
        title = re.sub(r"[\U00010000-\U0010ffff]", "", title)
        title = re.sub(r"\s+", " ", title).strip(" -|·•\t\n")
        if len(title) > 48:
            title = title[:47].rstrip() + "…"
        return title or "오늘의 IT 핵심 이슈"

    def _render_title_overlay_image(self, width: int = 1080, height: int = 292):
        """Render a persistent top title banner as a transparent RGBA image."""
        from PIL import ImageDraw, ImageFont

        text = self._overlay_title_text()
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        font_path = self._subtitle_font_path()
        font = ImageFont.truetype(font_path, 49)
        badge_font = ImageFont.truetype(font_path, 31)
        stroke_width = 4

        # Top-safe title card: high enough to avoid subtitles, low enough for mobile safe margins.
        box_x, box_y = 46, 44
        box_w, box_h = width - 92, 196
        draw.rounded_rectangle(
            (box_x, box_y, box_x + box_w, box_y + box_h),
            radius=34,
            fill=(0, 0, 0, 178),
            outline=(255, 230, 70, 230),
            width=3,
        )
        draw.rounded_rectangle((box_x + 28, box_y + 32, box_x + 142, box_y + 78), radius=18, fill=(255, 224, 52, 245))
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

        # If the second line is still too wide, trim only the tail.
        for idx, line in enumerate(lines[:2]):
            display = line
            while display:
                bbox = draw.textbbox((0, 0), display, font=font, stroke_width=stroke_width)
                if bbox[2] - bbox[0] <= max_text_width or len(display) <= 8:
                    break
                display = display[:-2].rstrip() + "…"
            lines[idx] = display

        line_metrics = [draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width) for line in lines[:2]]
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

    def _create_title_overlay_clip(self, duration: float):
        """Create a full-duration top title overlay clip."""
        image = self._render_title_overlay_image()
        return (
            ImageClip(np.array(image))
            .set_start(0)
            .set_duration(max(0.1, float(duration or 0.1)))
            .set_position(("center", 0))
        )

    def generate_subtitles(self, audio_path: str) -> str:
        """
        Generates subtitles for the audio using the configured STT provider.

        Args:
            audio_path (str): The path to the audio file.

        Returns:
            path (str): The path to the generated SRT File.
        """
        provider = str(get_stt_provider() or "local_whisper").lower()

        if provider == "local_whisper":
            return self.generate_subtitles_local_whisper(audio_path)

        if provider == "third_party_assemblyai":
            return self.generate_subtitles_assemblyai(audio_path)

        warning(f"Unknown stt_provider '{provider}'. Falling back to local_whisper.")
        return self.generate_subtitles_local_whisper(audio_path)

    def generate_subtitles_assemblyai(self, audio_path: str) -> str:
        """
        Generates subtitles using AssemblyAI.

        Args:
            audio_path (str): Audio file path

        Returns:
            path (str): Path to SRT file
        """
        aai.settings.api_key = get_assemblyai_api_key()
        config = aai.TranscriptionConfig()
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(audio_path)
        subtitles = transcript.export_subtitles_srt()

        srt_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".srt")

        with open(srt_path, "w") as file:
            file.write(subtitles)

        return srt_path

    def _format_srt_timestamp(self, seconds: float) -> str:
        """
        Formats a timestamp in seconds to SRT format.

        Args:
            seconds (float): Seconds

        Returns:
            ts (str): HH:MM:SS,mmm
        """
        total_millis = max(0, int(round(seconds * 1000)))
        hours = total_millis // 3600000
        minutes = (total_millis % 3600000) // 60000
        secs = (total_millis % 60000) // 1000
        millis = total_millis % 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def generate_subtitles_local_whisper(self, audio_path: str) -> str:
        """
        Generates subtitles using local Whisper (faster-whisper).

        Args:
            audio_path (str): Audio file path

        Returns:
            path (str): Path to SRT file
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            error(
                "Local STT selected but 'faster-whisper' is not installed. "
                "Install it or switch stt_provider to third_party_assemblyai."
            )
            raise

        model = WhisperModel(
            get_whisper_model(),
            device=get_whisper_device(),
            compute_type=get_whisper_compute_type(),
        )
        segments, _ = model.transcribe(audio_path, vad_filter=True)

        lines = []
        for idx, segment in enumerate(segments, start=1):
            start = self._format_srt_timestamp(segment.start)
            end = self._format_srt_timestamp(segment.end)
            text = str(segment.text).strip()

            if not text:
                continue

            lines.append(str(idx))
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")

        subtitles = "\n".join(lines)
        srt_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".srt")
        with open(srt_path, "w", encoding="utf-8") as file:
            file.write(subtitles)

        return srt_path

    def combine(self) -> str:
        """
        Combines everything into the final video.

        Returns:
            path (str): The path to the generated MP4 File.
        """
        combined_image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".mp4")
        threads = get_threads()
        tts_clip = AudioFileClip(self.tts_path)
        max_duration = tts_clip.duration
        req_dur = max_duration / len(self.images)

        # Make a generator that returns a TextClip when called with consecutive
        generator = lambda txt: TextClip(
            txt,
            font=os.path.join(get_fonts_dir(), get_font()),
            fontsize=100,
            color="#FFFF00",
            stroke_color="black",
            stroke_width=5,
            size=(1080, 1920),
            method="caption",
        )

        print(colored("[+] Combining images...", "blue"))

        clips = []
        tot_dur = 0
        # Add downloaded clips over and over until the duration of the audio (max_duration) has been reached
        while tot_dur < max_duration:
            for image_path in self.images:
                clip = ImageClip(image_path)
                clip.duration = req_dur
                clip = clip.set_fps(30)

                # Not all images are same size,
                # so we need to resize them
                if round((clip.w / clip.h), 4) < 0.5625:
                    if get_verbose():
                        info(f" => Resizing Image: {image_path} to 1080x1920")
                    clip = crop(
                        clip,
                        width=clip.w,
                        height=round(clip.w / 0.5625),
                        x_center=clip.w / 2,
                        y_center=clip.h / 2,
                    )
                else:
                    if get_verbose():
                        info(f" => Resizing Image: {image_path} to 1920x1080")
                    clip = crop(
                        clip,
                        width=round(0.5625 * clip.h),
                        height=clip.h,
                        x_center=clip.w / 2,
                        y_center=clip.h / 2,
                    )
                clip = clip.resize((1080, 1920))

                # FX (Fade In)
                # clip = clip.fadein(2)

                clips.append(clip)
                tot_dur += clip.duration

        final_clip = concatenate_videoclips(clips)
        final_clip = final_clip.set_fps(30)
        random_song = choose_random_song()

        subtitles = []
        try:
            subtitles_path = self.generate_safe_subtitles(self.tts_path, tts_clip.duration)
            try:
                equalize_subtitles(subtitles_path, 10)
            except Exception as e:
                warning(f"Failed to equalize subtitles, using raw subtitles: {e}")
            subtitles = self._create_subtitle_clips(subtitles_path)
            self.subtitles_path = subtitles_path
        except Exception as e:
            warning(f"Failed to create subtitles, continuing without subtitles: {e}")

        random_song_clip = AudioFileClip(random_song).set_fps(44100)

        # Turn down volume
        random_song_clip = random_song_clip.fx(afx.volumex, 0.1)
        comp_audio = CompositeAudioClip([tts_clip.set_fps(44100), random_song_clip])

        final_clip = final_clip.set_audio(comp_audio)
        final_clip = final_clip.set_duration(tts_clip.duration)

        title_overlay = self._create_title_overlay_clip(tts_clip.duration)
        overlay_clips = [final_clip, title_overlay, *subtitles]
        final_clip = CompositeVideoClip(overlay_clips)

        final_clip.write_videofile(combined_image_path, threads=threads)

        success(f'Wrote Video to "{combined_image_path}"')

        return combined_image_path

    def generate_video(self, tts_instance: TTS) -> str:
        """
        Generates a YouTube Short based on the provided niche and language.

        Args:
            tts_instance (TTS): Instance of TTS Class.

        Returns:
            path (str): The path to the generated MP4 File.
        """
        # Generate the Topic
        self.generate_topic()

        # Generate the Script
        self.generate_script()

        # Generate the Metadata
        self.generate_metadata()

        # Generate the Image Prompts
        self.generate_prompts()

        # Generate the Images
        for prompt in self.image_prompts:
            self.generate_image(prompt)

        # Generate the TTS
        self.generate_script_to_speech(tts_instance)

        # Combine everything
        path = self.combine()

        if get_verbose():
            info(f" => Generated Video: {path}")

        self.video_path = os.path.abspath(path)

        return path

    def generate_video_from_news(self, tts_instance: TTS, article: dict) -> str:
        """
        Generates a YouTube Short from a ranked tech-news article.

        Args:
            tts_instance (TTS): Instance of TTS Class.
            article (dict): Ranked/normalized article from news.collector.

        Returns:
            path (str): The path to the generated MP4 File.
        """
        self.news_article = article
        try:
            return self.generate_video(tts_instance)
        finally:
            self.news_article = None

    def get_channel_id(self) -> str:
        """
        Gets the Channel ID of the YouTube Account.

        Returns:
            channel_id (str): The Channel ID.
        """
        driver = self.browser
        driver.get("https://studio.youtube.com")
        time.sleep(2)
        channel_id = driver.current_url.split("/")[-1]
        self.channel_id = channel_id

        return channel_id

    def upload_video(self) -> bool:
        """
        Uploads the video to YouTube.

        Returns:
            success (bool): Whether the upload was successful or not.
        """
        try:
            self.get_channel_id()

            driver = self.browser
            verbose = get_verbose()

            # Go to youtube.com/upload
            driver.get("https://www.youtube.com/upload")

            # Set video file
            FILE_PICKER_TAG = "ytcp-uploads-file-picker"
            file_picker = driver.find_element(By.TAG_NAME, FILE_PICKER_TAG)
            INPUT_TAG = "input"
            file_input = file_picker.find_element(By.TAG_NAME, INPUT_TAG)
            file_input.send_keys(self.video_path)

            # Wait for upload to finish
            time.sleep(5)

            # Set title
            textboxes = driver.find_elements(By.ID, YOUTUBE_TEXTBOX_ID)

            title_el = textboxes[0]
            description_el = textboxes[-1]

            if verbose:
                info("\t=> Setting title...")

            title_el.click()
            time.sleep(1)
            title_el.clear()
            title_el.send_keys(self.metadata["title"])

            if verbose:
                info("\t=> Setting description...")

            # Set description
            time.sleep(10)
            description_el.click()
            time.sleep(0.5)
            description_el.clear()
            description_el.send_keys(self.metadata["description"])

            time.sleep(0.5)

            # Set `made for kids` option
            if verbose:
                info("\t=> Setting `made for kids` option...")

            is_for_kids_checkbox = driver.find_element(
                By.NAME, YOUTUBE_MADE_FOR_KIDS_NAME
            )
            is_not_for_kids_checkbox = driver.find_element(
                By.NAME, YOUTUBE_NOT_MADE_FOR_KIDS_NAME
            )

            if not get_is_for_kids():
                is_not_for_kids_checkbox.click()
            else:
                is_for_kids_checkbox.click()

            time.sleep(0.5)

            # Click next
            if verbose:
                info("\t=> Clicking next...")

            next_button = driver.find_element(By.ID, YOUTUBE_NEXT_BUTTON_ID)
            next_button.click()

            # Click next again
            if verbose:
                info("\t=> Clicking next again...")
            next_button = driver.find_element(By.ID, YOUTUBE_NEXT_BUTTON_ID)
            next_button.click()

            # Wait for 2 seconds
            time.sleep(2)

            # Click next again
            if verbose:
                info("\t=> Clicking next again...")
            next_button = driver.find_element(By.ID, YOUTUBE_NEXT_BUTTON_ID)
            next_button.click()

            # Set as unlisted
            if verbose:
                info("\t=> Setting as unlisted...")

            radio_button = driver.find_elements(By.XPATH, YOUTUBE_RADIO_BUTTON_XPATH)
            radio_button[2].click()

            if verbose:
                info("\t=> Clicking done button...")

            # Click done button
            done_button = driver.find_element(By.ID, YOUTUBE_DONE_BUTTON_ID)
            done_button.click()

            # Wait for 2 seconds
            time.sleep(2)

            # Get latest video
            if verbose:
                info("\t=> Getting video URL...")

            # Get the latest uploaded video URL
            driver.get(
                f"https://studio.youtube.com/channel/{self.channel_id}/videos/short"
            )
            time.sleep(2)
            videos = driver.find_elements(By.TAG_NAME, "ytcp-video-row")
            first_video = videos[0]
            anchor_tag = first_video.find_element(By.TAG_NAME, "a")
            href = anchor_tag.get_attribute("href")
            if verbose:
                info(f"\t=> Extracting video ID from URL: {href}")
            video_id = href.split("/")[-2]

            # Build URL
            url = build_url(video_id)

            self.uploaded_video_url = url

            if verbose:
                success(f" => Uploaded Video: {url}")

            # Add video to cache
            self.add_video(
                {
                    "title": self.metadata["title"],
                    "description": self.metadata["description"],
                    "url": url,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

            # Close the browser
            driver.quit()

            return True
        except:
            self.browser.quit()
            return False

    def get_videos(self) -> List[dict]:
        """
        Gets the uploaded videos from the YouTube Channel.

        Returns:
            videos (List[dict]): The uploaded videos.
        """
        if not os.path.exists(get_youtube_cache_path()):
            # Create the cache file
            with open(get_youtube_cache_path(), "w") as file:
                json.dump({"videos": []}, file, indent=4)
            return []

        videos = []
        # Read the cache file
        with open(get_youtube_cache_path(), "r") as file:
            previous_json = json.loads(file.read())
            # Find our account
            accounts = previous_json["accounts"]
            for account in accounts:
                if account["id"] == self._account_uuid:
                    videos = account["videos"]

        return videos
