import re
import base64
import json
import time
import os
import requests
import numpy as np

try:
    import assemblyai as aai
except ImportError:
    aai = None

from utils import *
from cache import *
from .Tts import TTS
from llm_provider import generate_text
from config import *
from status import *
from uuid import uuid4
from constants import *
from typing import List
from moviepy.editor import AudioFileClip
from moviepy.editor import CompositeAudioClip
from moviepy.editor import CompositeVideoClip
from moviepy.editor import ImageClip
from moviepy.editor import concatenate_videoclips
from moviepy.editor import afx
from termcolor import colored
from moviepy.video.fx.all import crop
from moviepy.config import change_settings
from datetime import datetime
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.firefox.service import Service
    from selenium.webdriver.firefox.options import Options
    from webdriver_manager.firefox import GeckoDriverManager
except ImportError:
    webdriver = None
    By = None
    Service = None
    Options = None
    GeckoDriverManager = None

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
        init_browser: bool = True,
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

        self.options = None
        self.service = None
        self.browser = None

        if not init_browser:
            return

        if any(item is None for item in (webdriver, By, Service, Options, GeckoDriverManager)):
            raise RuntimeError(
                "Browser automation dependencies are not installed. "
                "Install selenium, webdriver_manager, and selenium_firefox."
            )

        # Initialize the Firefox profile
        self.options: Options = Options()

        # Set headless state of browser
        if get_headless():
            self.options.add_argument("--headless")

        if not os.path.isdir(self._fp_profile_path):
            raise ValueError(
                f"Firefox profile path does not exist or is not a directory: {self._fp_profile_path}"
            )

        self.options.add_argument("-profile")
        self.options.add_argument(self._fp_profile_path)

        # Set the service
        self.service: Service = Service(GeckoDriverManager().install())

        # Initialize the browser
        self.browser: webdriver.Firefox = webdriver.Firefox(
            service=self.service, options=self.options
        )

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
        return generate_text(prompt, model_name=model_name)

    def generate_topic(self) -> str:
        """
        Generates a topic based on the YouTube Channel niche.

        Returns:
            topic (str): The generated topic.
        """
        completion = self.generate_response(
            f"Please generate a specific video idea that takes about the following topic: {self.niche}. Make it exactly one sentence. Only return the topic, nothing else."
        )

        if not completion:
            error("Failed to generate Topic.")

        self.subject = completion

        return completion

    def generate_script(self) -> str:
        """
        Generate a script for a video, depending on the subject of the video, the number of paragraphs, and the AI model.

        Returns:
            script (str): The script of the video.
        """
        sentence_length = get_script_sentence_length()
        prompt = f"""
        Generate a script for a video in {sentence_length} sentences, depending on the subject of the video.

        The script is to be returned as a string with the specified number of paragraphs.

        Here is an example of a string:
        "This is an example string."

        Do not under any circumstance reference this prompt in your response.

        Get straight to the point, don't start with unnecessary things like, "welcome to this video".

        Obviously, the script should be related to the subject of the video.
        
        YOU MUST NOT EXCEED THE {sentence_length} SENTENCES LIMIT. MAKE SURE THE {sentence_length} SENTENCES ARE SHORT.
        YOU MUST NOT INCLUDE ANY TYPE OF MARKDOWN OR FORMATTING IN THE SCRIPT, NEVER USE A TITLE.
        YOU MUST WRITE THE SCRIPT IN THE LANGUAGE SPECIFIED IN [LANGUAGE].
        ONLY RETURN THE RAW CONTENT OF THE SCRIPT. DO NOT INCLUDE "VOICEOVER", "NARRATOR" OR SIMILAR INDICATORS OF WHAT SHOULD BE SPOKEN AT THE BEGINNING OF EACH PARAGRAPH OR LINE. YOU MUST NOT MENTION THE PROMPT, OR ANYTHING ABOUT THE SCRIPT ITSELF. ALSO, NEVER TALK ABOUT THE AMOUNT OF PARAGRAPHS OR LINES. JUST WRITE THE SCRIPT
        
        Subject: {self.subject}
        Language: {self.language}
        """
        completion = self.generate_response(prompt)

        # Apply regex to remove *
        completion = re.sub(r"\*", "", completion)

        if not completion:
            error("The generated script is empty.")
            return

        if len(completion) > 5000:
            if get_verbose():
                warning("Generated Script is too long. Retrying...")
            return self.generate_script()

        self.script = completion

        return completion

    def generate_news_script(self, news_context: str) -> str:
        """
        Generates a Shorts voiceover script from a selected news article.
        """
        sentence_length = get_script_sentence_length()
        prompt = f"""
        Write a YouTube Shorts voiceover script in {sentence_length} short sentences.

        Use the article context below as the factual source.
        Mention the article date when it is available, using a natural phrase near the beginning.
        Make the first sentence a strong hook.
        Explain why ordinary viewers should care about the device or technology.
        Avoid speculation beyond the article.

        YOU MUST WRITE IN THE LANGUAGE SPECIFIED IN [LANGUAGE].
        ONLY RETURN THE RAW SPOKEN SCRIPT.
        DO NOT INCLUDE MARKDOWN, TITLES, LABELS, HASHTAGS, OR SOURCE URLS.
        DO NOT EXCEED {sentence_length} SENTENCES.

        [LANGUAGE]
        {self.language}

        [ARTICLE CONTEXT]
        {news_context}
        """
        completion = re.sub(r"\*", "", self.generate_response(prompt)).strip()

        if not completion:
            error("The generated news script is empty.")
            return

        self.script = completion
        return completion

    def generate_video_from_news(
        self,
        news_context: str,
        subject: str,
        tts_instance: TTS,
        article_image_url: str = "",
    ) -> str:
        """
        Generates a local YouTube Short from a news article context.
        """
        self.subject = subject
        self.generate_news_script(news_context)
        self.generate_metadata()
        self.generate_prompts()

        for prompt in self.image_prompts:
            self.generate_image(prompt)

        if not self.images:
            self.create_contextual_thumbnail(subject)

        if not self.images and article_image_url:
            self.download_image(article_image_url)

        self.generate_script_to_speech(tts_instance)
        path = self.combine()
        self.video_path = os.path.abspath(path)
        return path

    def generate_metadata(self) -> dict:
        """
        Generates Video metadata for the to-be-uploaded YouTube Short (Title, Description).

        Returns:
            metadata (dict): The generated metadata.
        """
        title = self.generate_response(
            f"Please generate one YouTube Shorts title for this subject: {self.subject}. "
            "Only return the title. Keep it under 90 characters including hashtags."
        ).strip()

        if len(title) > 100:
            if get_verbose():
                warning("Generated Title is too long. Truncating to fit YouTube limit.")
            title = title[:97].rstrip() + "..."

        description = self.generate_response(
            f"Please generate a YouTube Video Description for the following script: {self.script}. Only return the description, nothing else."
        )

        self.metadata = {"title": title, "description": description}

        return self.metadata

    def generate_prompts(self) -> List[str]:
        """
        Generates AI Image Prompts based on the provided Video Script.

        Returns:
            image_prompts (List[str]): Generated List of image prompts.
        """
        sentence_count = len(re.findall(r"[.!?]+", self.script))
        n_prompts = max(3, min(6, sentence_count or get_script_sentence_length()))

        prompt = f"""
        Generate {n_prompts} Image Prompts for AI Image Generation,
        depending on the subject of a video.
        Subject: {self.subject}

        The image prompts are to be returned as
        a JSON-Array of strings.

        Each search term should consist of a full sentence,
        always add the main subject of the video.

        Be emotional and use interesting adjectives to make the
        Image Prompt as detailed as possible.

        YOU MUST ONLY RETURN THE JSON-ARRAY OF STRINGS.
        YOU MUST NOT RETURN ANYTHING ELSE.
        YOU MUST NOT RETURN THE SCRIPT.

        The search terms must be related to the subject of the video.
        Here is an example of a JSON-Array of strings:
        ["image prompt 1", "image prompt 2", "image prompt 3"]

        For context, here is the full text:
        {self.script}
        """

        completion = (
            str(self.generate_response(prompt))
            .replace("```json", "")
            .replace("```", "")
        )

        image_prompts = []

        try:
            if "image_prompts" in completion:
                image_prompts = json.loads(completion)["image_prompts"]
            else:
                image_prompts = json.loads(completion)
                if get_verbose():
                    info(f" => Generated Image Prompts: {image_prompts}")
        except Exception:
            if get_verbose():
                warning("LLM returned an unformatted response. Attempting to clean...")

            # Get everything between [ and ], and turn it into a list
            r = re.compile(r"\[.*\]", flags=re.DOTALL)
            matches = r.findall(completion)
            if matches:
                try:
                    image_prompts = json.loads(matches[0])
                except Exception:
                    image_prompts = []

        if not isinstance(image_prompts, list):
            image_prompts = []

        image_prompts = [
            str(prompt).strip()
            for prompt in image_prompts
            if str(prompt).strip()
        ]

        if len(image_prompts) == 0:
            if get_verbose():
                warning("Failed to parse Image Prompts. Using fallback prompts.")
            image_prompts = self.generate_fallback_prompts(n_prompts)

        if len(image_prompts) > n_prompts:
            image_prompts = image_prompts[: int(n_prompts)]

        self.image_prompts = image_prompts

        success(f"Generated {len(image_prompts)} Image Prompts.")

        return image_prompts

    def generate_fallback_prompts(self, n_prompts: int) -> List[str]:
        """
        Builds reliable image prompts when the LLM does not return valid JSON.

        Args:
            n_prompts (int): Desired prompt count

        Returns:
            prompts (List[str]): Fallback image prompts
        """
        subject = str(getattr(self, "subject", self.niche)).strip()
        base_prompt = (
            f"Vertical 9:16 cinematic editorial illustration about {subject}, "
            "premium technology news visual, dramatic lighting, sharp detail, "
            "clean composition, no text, no logos."
        )
        variations = [
            "Close-up hero shot of a modern laptop concept on a dark studio background, no hands, no people.",
            "Exploded-view inspired scene showing modular laptop parts and premium materials, no hands, no people.",
            "Clean product scene of an open laptop in a modern workspace, no hands, no people.",
            "Abstract technology backdrop with glass, aluminum, and soft reflections.",
            "High-energy YouTube Shorts thumbnail style, bold contrast, realistic depth.",
            "Minimal futuristic product render with strong vertical framing.",
        ]
        if "framework" in subject.lower() or "laptop" in subject.lower():
            variations = [
                "Open premium modular laptop, the word Framework clearly visible on the laptop screen, no hands, no people.",
                "Closed aluminum laptop lid with the word Framework, modular expansion ports visible, no hands, no people.",
                "Exploded-view modular laptop parts around a central Framework laptop, no hands, no people.",
                "Clean studio product render of a Framework-style laptop on a dark reflective surface, no hands, no people.",
            ]
        return [
            f"{base_prompt} {variation}"
            for variation in variations[: max(1, int(n_prompts))]
        ]

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

        endpoint = f"{base_url}/models/{model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": aspect_ratio},
            },
        }

        try:
            response = requests.post(
                endpoint,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=300,
            )
            response.raise_for_status()
            body = response.json()

            candidates = body.get("candidates", [])
            for candidate in candidates:
                content = candidate.get("content", {})
                for part in content.get("parts", []):
                    inline_data = part.get("inlineData") or part.get("inline_data")
                    if not inline_data:
                        continue
                    data = inline_data.get("data")
                    mime_type = inline_data.get("mimeType") or inline_data.get("mime_type", "")
                    if data and str(mime_type).startswith("image/"):
                        image_bytes = base64.b64decode(data)
                        return self._persist_image(image_bytes, "Nano Banana 2 API")

            if get_verbose():
                warning(f"Nano Banana 2 did not return an image payload. Response: {body}")
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
        return self.generate_image_nanobanana2(prompt)

    def download_image(self, image_url: str) -> str:
        """
        Downloads an existing image to use as a fallback visual.
        """
        if not image_url:
            return None

        response = requests.get(image_url, timeout=60)
        response.raise_for_status()
        return self._persist_image(response.content, "article image")

    def create_contextual_thumbnail(self, subject: str) -> str:
        """
        Creates a topic-fit fallback thumbnail when AI image generation is unavailable.
        """
        plan = self._build_thumbnail_plan(subject)
        width = 1080
        height = 1920
        image = Image.new("RGB", (width, height), "#081018")
        draw = ImageDraw.Draw(image)

        top_color = plan["top_color"]
        bottom_color = plan["bottom_color"]
        for y in range(height):
            blend = y / height
            r = int(top_color[0] + (bottom_color[0] - top_color[0]) * blend)
            g = int(top_color[1] + (bottom_color[1] - top_color[1]) * blend)
            b = int(top_color[2] + (bottom_color[2] - top_color[2]) * blend)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        accent = plan["accent"]
        shadow = (0, 0, 0)
        font_title = self._load_font(74, bold=True)
        font_brand = self._load_font(88, bold=True)
        font_small = self._load_font(38, bold=True)

        draw.rounded_rectangle(
            (80, 250, 1000, 1510),
            radius=46,
            fill=(0, 0, 0, 95),
            outline=(55, 75, 90),
            width=3,
        )

        headline_lines = plan["headline_lines"]
        y = 300
        for line in headline_lines:
            bbox = draw.textbbox((0, 0), line, font=font_title, stroke_width=5)
            x = (width - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=font_title, fill="white", stroke_width=5, stroke_fill=shadow)
            y += 92

        self._draw_thumbnail_subject(draw, plan, font_brand)

        badge = plan["badge"]
        badge_bbox = draw.textbbox((0, 0), badge, font=font_small, stroke_width=3)
        badge_x = (width - (badge_bbox[2] - badge_bbox[0])) // 2
        draw.rounded_rectangle((badge_x - 28, 1440, badge_x + badge_bbox[2] - badge_bbox[0] + 28, 1515), radius=22, fill=accent)
        draw.text((badge_x, 1454), badge, font=font_small, fill="#101010", stroke_width=0)

        image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")
        image.save(image_path)
        if get_verbose():
            info(f' => Wrote contextual thumbnail to "{image_path}"')
        self.images.append(image_path)
        return image_path

    def _build_thumbnail_plan(self, subject: str) -> dict:
        """
        Converts a news subject into a reusable thumbnail plan.
        """
        normalized = str(subject or "").lower()
        brand = self._extract_thumbnail_brand(subject)

        if any(token in normalized for token in ("laptop", "notebook", "macbook", "framework", "pc")):
            return {
                "kind": "laptop",
                "brand": brand or "LAPTOP",
                "headline_lines": ["신형 노트북", "핵심만 보기"],
                "badge": "제품 중심 썸네일",
                "top_color": (5, 14, 22),
                "bottom_color": (35, 48, 68),
                "accent": (255, 230, 0),
            }

        if any(token in normalized for token in ("phone", "iphone", "galaxy", "smartphone", "xiaomi", "pixel")):
            return {
                "kind": "phone",
                "brand": brand or "PHONE",
                "headline_lines": ["스마트폰 소식", "바로 정리"],
                "badge": "손 없는 제품 컷",
                "top_color": (8, 9, 26),
                "bottom_color": (26, 58, 90),
                "accent": (0, 230, 255),
            }

        if any(token in normalized for token in ("chip", "gpu", "cpu", "semiconductor", "qualcomm", "nvidia", "mediatek", "tsmc")):
            return {
                "kind": "chip",
                "brand": brand or "CHIP",
                "headline_lines": ["칩셋 업데이트", "성능 포인트"],
                "badge": "반도체 뉴스",
                "top_color": (6, 18, 16),
                "bottom_color": (18, 72, 54),
                "accent": (20, 255, 150),
            }

        if any(token in normalized for token in ("battery", "charging", "silicon-carbon")):
            return {
                "kind": "battery",
                "brand": brand or "BATTERY",
                "headline_lines": ["배터리 변화", "왜 중요할까"],
                "badge": "기술 포인트",
                "top_color": (16, 18, 8),
                "bottom_color": (70, 72, 20),
                "accent": (210, 255, 0),
            }

        if any(token in normalized for token in ("display", "oled", "foldable", "screen", "monitor")):
            return {
                "kind": "display",
                "brand": brand or "DISPLAY",
                "headline_lines": ["디스플레이 뉴스", "핵심 변화"],
                "badge": "화면 기술",
                "top_color": (12, 8, 30),
                "bottom_color": (58, 28, 92),
                "accent": (190, 120, 255),
            }

        return {
            "kind": "generic",
            "brand": brand or "TECH",
            "headline_lines": ["테크 뉴스", "핵심 요약"],
            "badge": "주제 맞춤 썸네일",
            "top_color": (8, 16, 24),
            "bottom_color": (34, 50, 70),
            "accent": (255, 230, 0),
        }

    def _extract_thumbnail_brand(self, subject: str) -> str:
        """
        Extracts a compact brand label for generated thumbnails.
        """
        known_brands = [
            "Framework",
            "Apple",
            "Samsung",
            "Galaxy",
            "Qualcomm",
            "Nvidia",
            "AMD",
            "Intel",
            "MediaTek",
            "TSMC",
            "Sony",
            "Xiaomi",
            "Google",
        ]
        lowered = str(subject or "").lower()
        for brand in known_brands:
            if brand.lower() in lowered:
                return brand
        return ""

    def _draw_thumbnail_subject(self, draw, plan: dict, font_brand) -> None:
        """
        Draws a generic product-like subject without humans or hands.
        """
        kind = plan["kind"]
        if kind == "laptop":
            self._draw_laptop_thumbnail(draw, plan, font_brand)
        elif kind == "phone":
            self._draw_phone_thumbnail(draw, plan, font_brand)
        elif kind == "chip":
            self._draw_chip_thumbnail(draw, plan, font_brand)
        elif kind == "battery":
            self._draw_battery_thumbnail(draw, plan, font_brand)
        elif kind == "display":
            self._draw_display_thumbnail(draw, plan, font_brand)
        else:
            self._draw_generic_thumbnail(draw, plan, font_brand)

    def _draw_centered_text(self, draw, text: str, y: int, font, fill, stroke_width: int = 4) -> None:
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        x = (1080 - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=(0, 0, 0))

    def _draw_laptop_thumbnail(self, draw, plan: dict, font_brand) -> None:
        accent = plan["accent"]
        draw.rounded_rectangle((145, 560, 935, 1130), radius=28, fill=(12, 16, 23), outline=(95, 112, 125), width=5)
        draw.rectangle((185, 615, 895, 1070), fill=(20, 30, 42))
        draw.line((185, 615, 895, 1070), fill=(45, 65, 85), width=3)
        draw.line((895, 615, 185, 1070), fill=(32, 48, 68), width=2)
        self._draw_centered_text(draw, plan["brand"], 790, font_brand, accent)
        draw.polygon([(115, 1160), (965, 1160), (1040, 1320), (40, 1320)], fill=(34, 39, 46), outline=(105, 120, 132))
        draw.rounded_rectangle((195, 1202, 885, 1278), radius=18, fill=(22, 26, 30))
        for idx, x in enumerate((150, 235, 760, 845)):
            draw.rounded_rectangle((x, 1340, x + 70, 1375), radius=8, fill=accent if idx % 2 == 0 else (0, 210, 255))

    def _draw_phone_thumbnail(self, draw, plan: dict, font_brand) -> None:
        accent = plan["accent"]
        draw.rounded_rectangle((320, 550, 760, 1265), radius=58, fill=(18, 22, 30), outline=(130, 150, 165), width=6)
        draw.rounded_rectangle((352, 600, 728, 1208), radius=36, fill=(15, 25, 42))
        draw.ellipse((500, 570, 580, 590), fill=(8, 10, 15))
        self._draw_centered_text(draw, plan["brand"], 820, font_brand, accent)
        draw.rounded_rectangle((398, 1040, 682, 1108), radius=20, fill=accent)

    def _draw_chip_thumbnail(self, draw, plan: dict, font_brand) -> None:
        accent = plan["accent"]
        draw.rounded_rectangle((270, 600, 810, 1140), radius=42, fill=(20, 35, 32), outline=accent, width=8)
        for x in range(210, 870, 80):
            draw.rectangle((x, 820, x + 36, 880), fill=accent)
        for y in range(550, 1200, 80):
            draw.rectangle((500, y, 580, y + 34), fill=accent)
        self._draw_centered_text(draw, plan["brand"], 810, font_brand, accent)
        for x in (180, 900):
            for y in (650, 760, 990, 1100):
                draw.line((x, y, 270 if x < 500 else 810, y), fill=(90, 255, 190), width=4)

    def _draw_battery_thumbnail(self, draw, plan: dict, font_brand) -> None:
        accent = plan["accent"]
        draw.rounded_rectangle((210, 690, 820, 1080), radius=48, fill=(20, 28, 25), outline=accent, width=8)
        draw.rounded_rectangle((820, 805, 890, 965), radius=20, fill=accent)
        draw.rounded_rectangle((260, 750, 760, 1020), radius=32, fill=(42, 72, 38))
        draw.rectangle((260, 750, 660, 1020), fill=accent)
        self._draw_centered_text(draw, plan["brand"], 1140, font_brand, accent)

    def _draw_display_thumbnail(self, draw, plan: dict, font_brand) -> None:
        accent = plan["accent"]
        draw.rounded_rectangle((200, 580, 540, 1190), radius=34, fill=(20, 18, 32), outline=accent, width=6)
        draw.rounded_rectangle((540, 620, 880, 1150), radius=34, fill=(26, 22, 40), outline=(225, 180, 255), width=6)
        draw.line((540, 640, 540, 1140), fill=(90, 70, 120), width=10)
        self._draw_centered_text(draw, plan["brand"], 820, font_brand, accent)

    def _draw_generic_thumbnail(self, draw, plan: dict, font_brand) -> None:
        accent = plan["accent"]
        draw.rounded_rectangle((230, 630, 850, 1180), radius=46, fill=(20, 30, 42), outline=accent, width=7)
        for idx, (x, y) in enumerate(((340, 760), (540, 700), (720, 840), (450, 1040), (680, 1050))):
            draw.ellipse((x - 36, y - 36, x + 36, y + 36), fill=accent)
            if idx:
                draw.line((540, 920, x, y), fill=(120, 180, 210), width=5)
        self._draw_centered_text(draw, plan["brand"], 850, font_brand, accent)

    def _load_font(self, size: int, bold: bool = False):
        """
        Loads a Korean-capable font for generated thumbnails.
        """
        candidates = []
        if bold:
            candidates.append(r"C:\Windows\Fonts\malgunbd.ttf")
        candidates.extend(
            [
                r"C:\Windows\Fonts\malgun.ttf",
                os.path.join(get_fonts_dir(), get_font()),
            ]
        )
        for font_path in candidates:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size)
        return ImageFont.load_default()

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

    def _contains_hangul(self, text: str) -> bool:
        """
        Returns True when the provided text contains Korean Hangul.
        """
        return bool(re.search(r"[가-힣]", str(text)))

    def generate_subtitles_from_script(self, duration: float) -> str:
        """
        Generates Korean subtitles directly from the approved voiceover script.

        Args:
            duration (float): Total audio duration in seconds

        Returns:
            path (str): Path to SRT file
        """
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?。！？])\s+|\n+", self.script)
            if sentence.strip()
        ]
        if not sentences:
            sentences = [self.script.strip()]

        total_chars = sum(max(1, len(sentence)) for sentence in sentences)
        cursor = 0.0
        lines = []

        for idx, sentence in enumerate(sentences, start=1):
            if idx == len(sentences):
                end = max(cursor + 0.5, duration)
            else:
                weight = max(1, len(sentence)) / total_chars
                end = min(duration, cursor + max(1.2, duration * weight))

            lines.append(str(idx))
            lines.append(
                f"{self._format_srt_timestamp(cursor)} --> {self._format_srt_timestamp(end)}"
            )
            lines.append(sentence)
            lines.append("")
            cursor = end

            if cursor >= duration:
                break

        srt_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".srt")
        with open(srt_path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines))

        return srt_path

    def generate_subtitles_assemblyai(self, audio_path: str) -> str:
        """
        Generates subtitles using AssemblyAI.

        Args:
            audio_path (str): Audio file path

        Returns:
            path (str): Path to SRT file
        """
        if aai is None:
            raise RuntimeError(
                "AssemblyAI subtitles requested but the 'assemblyai' package is not installed."
            )

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

    def _parse_srt_timestamp(self, value: str) -> float:
        """
        Parses an SRT timestamp into seconds.

        Args:
            value (str): Timestamp in HH:MM:SS,mmm format

        Returns:
            seconds (float): Parsed timestamp in seconds
        """
        cleaned = str(value).strip()
        hours, minutes, rest = cleaned.split(":")
        seconds, millis = rest.split(",")
        return (
            int(hours) * 3600
            + int(minutes) * 60
            + int(seconds)
            + int(millis) / 1000.0
        )

    def _parse_srt_entries(self, srt_path: str) -> List[dict]:
        """
        Parses an SRT file into timed subtitle entries.

        Args:
            srt_path (str): Path to SRT file

        Returns:
            entries (List[dict]): Subtitle entries
        """
        with open(srt_path, "r", encoding="utf-8") as file:
            raw_content = file.read().strip()

        if not raw_content:
            return []

        blocks = re.split(r"\r?\n\r?\n+", raw_content)
        entries = []

        for block in blocks:
            lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
            if len(lines) < 2:
                continue

            timing_line = lines[1] if "-->" in lines[1] else lines[0]
            if "-->" not in timing_line:
                continue

            start_raw, end_raw = [part.strip() for part in timing_line.split("-->")]
            text_lines = lines[2:] if timing_line == lines[1] else lines[1:]
            text = "\n".join(text_lines).strip()

            if not text:
                continue

            start = self._parse_srt_timestamp(start_raw)
            end = self._parse_srt_timestamp(end_raw)
            if end <= start:
                continue

            entries.append({"start": start, "end": end, "text": text})

        return entries

    def _wrap_subtitle_text(
        self,
        text: str,
        font: ImageFont.FreeTypeFont,
        max_width: int,
    ) -> str:
        """
        Wraps subtitle text to fit inside the target width.

        Args:
            text (str): Subtitle text
            font (ImageFont.FreeTypeFont): Font instance
            max_width (int): Maximum allowed line width

        Returns:
            wrapped (str): Wrapped subtitle text
        """
        dummy_image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        draw = ImageDraw.Draw(dummy_image)

        wrapped_lines = []
        for raw_line in str(text).splitlines():
            words = raw_line.split()
            if not words:
                wrapped_lines.append("")
                continue

            current_line = words[0]
            for word in words[1:]:
                candidate = f"{current_line} {word}"
                bbox = draw.multiline_textbbox((0, 0), candidate, font=font, spacing=12)
                width = bbox[2] - bbox[0]
                if width <= max_width:
                    current_line = candidate
                else:
                    wrapped_lines.append(current_line)
                    current_line = word
            wrapped_lines.append(current_line)

        return "\n".join(wrapped_lines)

    def _build_subtitle_clip(self, text: str, duration: float):
        """
        Builds a subtitle ImageClip using Pillow, avoiding ImageMagick.

        Args:
            text (str): Subtitle text
            duration (float): Clip duration

        Returns:
            clip (ImageClip): Subtitle clip
        """
        frame_width = 1080
        frame_height = 1920
        horizontal_padding = 90
        vertical_padding = 40
        bottom_margin = 220
        font_size = 84
        stroke_width = 6
        line_spacing = 12

        font_path = self._get_subtitle_font_path(text)
        font = ImageFont.truetype(font_path, font_size)
        wrapped_text = self._wrap_subtitle_text(
            text,
            font,
            frame_width - horizontal_padding * 2,
        )

        image = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        bbox = draw.multiline_textbbox(
            (0, 0),
            wrapped_text,
            font=font,
            spacing=line_spacing,
            stroke_width=stroke_width,
            align="center",
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = int((frame_width - text_width) / 2)
        y = int(frame_height - bottom_margin - text_height)

        background_bbox = (
            max(0, x - horizontal_padding // 2),
            max(0, y - vertical_padding // 2),
            min(frame_width, x + text_width + horizontal_padding // 2),
            min(frame_height, y + text_height + vertical_padding // 2),
        )
        draw.rounded_rectangle(
            background_bbox,
            radius=26,
            fill=(0, 0, 0, 135),
        )
        draw.multiline_text(
            (x, y),
            wrapped_text,
            font=font,
            fill=(255, 255, 0, 255),
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 255),
            spacing=line_spacing,
            align="center",
        )

        return ImageClip(np.array(image)).set_duration(duration).set_position(("center", "top"))

    def _get_subtitle_font_path(self, text: str) -> str:
        """
        Selects a subtitle font with Korean glyph support when needed.
        """
        if self._contains_hangul(text):
            korean_font_candidates = [
                r"C:\Windows\Fonts\malgunbd.ttf",
                r"C:\Windows\Fonts\malgun.ttf",
            ]
            for font_path in korean_font_candidates:
                if os.path.exists(font_path):
                    return font_path

        return os.path.join(get_fonts_dir(), get_font())

    def create_subtitles_overlay(self, srt_path: str):
        """
        Builds a subtitle overlay clip from an SRT file.

        Args:
            srt_path (str): Path to SRT file

        Returns:
            clip (CompositeVideoClip | None): Subtitle overlay clip
        """
        entries = self._parse_srt_entries(srt_path)
        if not entries:
            return None

        clips = []
        for entry in entries:
            duration = entry["end"] - entry["start"]
            clip = self._build_subtitle_clip(entry["text"], duration)
            clip = clip.set_start(entry["start"])
            clips.append(clip)

        if not clips:
            return None

        return CompositeVideoClip(clips, size=(1080, 1920))

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

        subtitles = None
        try:
            if self._contains_hangul(self.script):
                subtitles_path = self.generate_subtitles_from_script(tts_clip.duration)
            else:
                subtitles_path = self.generate_subtitles(self.tts_path)
                try:
                    equalize_subtitles(subtitles_path, 10)
                except Exception as e:
                    warning(f"Failed to equalize subtitles, using raw subtitles: {e}")
            subtitles = self.create_subtitles_overlay(subtitles_path)
        except Exception as e:
            warning(f"Failed to generate subtitles, continuing without subtitles: {e}")

        audio_layers = [tts_clip.set_fps(44100)]
        try:
            random_song = choose_random_song()
            random_song_clip = AudioFileClip(random_song).set_fps(44100)
            random_song_clip = random_song_clip.fx(afx.volumex, 0.1)
            audio_layers.append(random_song_clip)
        except Exception as e:
            warning(f"Failed to add background music, continuing without it: {e}")

        comp_audio = CompositeAudioClip(audio_layers)

        final_clip = final_clip.set_audio(comp_audio)
        final_clip = final_clip.set_duration(tts_clip.duration)

        if subtitles is not None:
            final_clip = CompositeVideoClip([final_clip, subtitles])

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
