import os
import json

try:
    from termcolor import colored
except ModuleNotFoundError:
    def colored(text, *_args, **_kwargs):
        return text

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_config_path() -> str:
    """Return the active config path, respecting tests that patch ROOT_DIR."""
    return os.path.join(ROOT_DIR, "config.json")


# Cache of the parsed config keyed by (path, mtime) so the dozens of getter
# functions don't re-read and re-parse config.json on every single call. The
# mtime check keeps live edits picked up without an explicit cache reset.
_config_cache: tuple[str, float, dict] | None = None


def load_config() -> dict:
    """Load the project config file (cached, invalidated on file mtime change)."""
    global _config_cache

    config_path = get_config_path()
    if not os.path.exists(config_path):
        example_path = os.path.join(ROOT_DIR, "config.example.json")
        if os.path.exists(example_path):
            config_path = example_path
        else:
            return {}

    try:
        mtime = os.path.getmtime(config_path)
    except OSError:
        mtime = -1.0

    if (
        _config_cache is not None
        and _config_cache[0] == config_path
        and _config_cache[1] == mtime
    ):
        # Return a copy so callers mutating the result can't corrupt the cache.
        return dict(_config_cache[2])

    with open(config_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        data = {}

    _config_cache = (config_path, mtime, data)
    return dict(data)


def get_config_value(key: str, default=None):
    """Read one top-level config value through the standard config fallback."""
    return load_config().get(key, default)


def load_env_file(path: str | None = None, override: bool = False) -> None:
    """Load simple KEY=VALUE pairs from a local .env file without extra dependencies."""
    env_path = path or os.path.join(ROOT_DIR, ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key:
                continue
            if override or key not in os.environ:
                os.environ[key] = value


def get_env_var(name: str, default: str = "") -> str:
    """Read env vars from the current process, then Docker PID 1 env if available."""
    value = os.environ.get(name, "")
    if value:
        return value

    # The Docker PID 1 fallback only exists on Linux; skip the probe elsewhere
    # (e.g. Windows, the project's primary target) to avoid a pointless open().
    if not os.path.exists("/proc/1/environ"):
        return default

    try:
        with open("/proc/1/environ", "rb") as file:
            for item in file.read().split(b"\0"):
                prefix = (name + "=").encode()
                if item.startswith(prefix):
                    return item[len(prefix):].decode("utf-8", "ignore")
    except OSError:
        pass

    return default


load_env_file()

def assert_folder_structure() -> None:
    """
    Make sure that the nessecary folder structure is present.

    Returns:
        None
    """
    # Create the .mp folder
    if not os.path.exists(os.path.join(ROOT_DIR, ".mp")):
        if get_verbose():
            print(colored(f"=> Creating .mp folder at {os.path.join(ROOT_DIR, '.mp')}", "green"))
        os.makedirs(os.path.join(ROOT_DIR, ".mp"))

def get_first_time_running() -> bool:
    """
    Checks if the program is running for the first time by checking if .mp folder exists.

    Returns:
        exists (bool): True if the program is running for the first time, False otherwise
    """
    return not os.path.exists(os.path.join(ROOT_DIR, ".mp"))

def get_email_credentials() -> dict:
    """
    Gets the email credentials from the config file.

    Returns:
        credentials (dict): The email credentials
    """
    return get_config_value("email", {})

def get_verbose() -> bool:
    """
    Gets the verbose flag from the config file.

    Returns:
        verbose (bool): The verbose flag
    """
    return bool(load_config().get("verbose", False))

def get_firefox_profile_path() -> str:
    """
    Gets the path to the Firefox profile.

    Returns:
        path (str): The path to the Firefox profile
    """
    return get_config_value("firefox_profile", "")

def get_headless() -> bool:
    """
    Gets the headless flag from the config file.

    Returns:
        headless (bool): The headless flag
    """
    return bool(get_config_value("headless", False))

def get_ollama_base_url() -> str:
    """
    Gets the Ollama base URL.

    Returns:
        url (str): The Ollama base URL
    """
    env_url = get_env_var("OLLAMA_BASE_URL", "").strip()
    if env_url:
        return env_url

    return get_config_value("ollama_base_url", "http://host.docker.internal:11434")

def get_ollama_model() -> str:
    """
    Gets the Ollama model name from the config file.

    Returns:
        model (str): The Ollama model name, or default gemma4:e4b if not set.
    """
    return load_config().get("ollama_model", "gemma4:e4b")


def get_text_provider() -> str:
    """
    Gets the text-generation provider.

    Supported values:
    - ollama: local Ollama chat API
    - gemini: Google Generative Language API when the selected model starts with gemini
    - hermes: Hermes CLI, usually backed by Codex gpt-5.6-sol on this machine
    """
    env_provider = get_env_var("TEXT_PROVIDER", "").strip()
    if env_provider:
        return env_provider.lower()
    return str(load_config().get("text_provider", "ollama")).strip().lower()


def get_hermes_model() -> str:
    """Gets the Hermes CLI model used for text generation."""
    env_model = get_env_var("HERMES_TEXT_MODEL", "").strip()
    if env_model:
        return env_model
    return str(load_config().get("hermes_model", "gpt-5.6-sol")).strip() or "gpt-5.6-sol"


def get_hermes_provider() -> str:
    """Gets the Hermes CLI provider used for text generation, when configured."""
    env_provider = get_env_var("HERMES_TEXT_PROVIDER", "").strip()
    if env_provider:
        return env_provider
    return str(load_config().get("hermes_provider", "")).strip()


def get_default_text_model() -> str:
    """Return the provider-aware default text model identifier."""
    provider = get_text_provider()
    if provider == "hermes":
        return f"hermes:{get_hermes_model()}"
    return get_ollama_model()


def get_script_review_enabled() -> bool:
    """
    Gets whether Shorts scripts should be reviewed once by local Ollama after initial generation.

    Returns:
        enabled (bool): True when script review is enabled.
    """
    env_value = get_env_var("SCRIPT_REVIEW_ENABLED", "").strip().lower()
    if env_value:
        return env_value not in ("0", "false", "no", "off")

    return bool(get_config_value("script_review_enabled", True))


def get_script_review_model() -> str:
    """
    Gets the Ollama model used for the post-generation script review.

    Returns:
        model (str): Review model name, defaulting to the normal Ollama model.
    """
    env_value = get_env_var("SCRIPT_REVIEW_MODEL", "").strip()
    if env_value:
        return env_value

    data = load_config()
    return data.get("script_review_model") or data.get("ollama_model", "gemma4:e4b")

def get_twitter_language() -> str:
    """
    Gets the Twitter language from the config file.

    Returns:
        language (str): The Twitter language
    """
    return get_config_value("twitter_language", "English")

def get_nanobanana2_api_base_url() -> str:
    """
    Gets the Nano Banana 2 (Gemini image) API base URL.

    Returns:
        url (str): API base URL
    """
    return get_config_value(
        "nanobanana2_api_base_url",
        "https://generativelanguage.googleapis.com/v1beta",
    )

def get_nanobanana2_api_key() -> str:
    """
    Gets the Nano Banana 2 API key.

    Returns:
        key (str): API key
    """
    configured = get_config_value("nanobanana2_api_key", "")
    return (
        configured
        or get_env_var("GEMINI_API_KEY", "")
        or get_env_var("GOOGLE_API_KEY", "")
    )

def get_nanobanana2_model() -> str:
    """
    Gets the Nano Banana 2 model name.

    Returns:
        model (str): Model name
    """
    return get_config_value("nanobanana2_model", "gemini-3.1-flash-image-preview")

def get_nanobanana2_aspect_ratio() -> str:
    """
    Gets the aspect ratio for Nano Banana 2 image generation.

    Returns:
        ratio (str): Aspect ratio
    """
    return get_config_value("nanobanana2_aspect_ratio", "9:16")

def get_image_provider() -> str:
    """
    Gets the image provider. Use 'gemini' for API image generation, 'hermes' to consume
    Hermes-agent-generated images from .mp/hermes_images/queue, and 'placeholder' only
    for local smoke tests.

    Returns:
        provider (str): Image provider name
    """
    env_provider = get_env_var("IMAGE_PROVIDER", "").strip()
    if env_provider:
        return env_provider.lower()

    return str(get_config_value("image_provider", "gemini")).lower()


def get_max_image_prompts() -> int:
    """
    Gets the maximum number of image prompts to use for a single Short.

    Returns:
        max_prompts (int): Prompt cap
    """
    value = get_config_value("max_image_prompts", 5)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 5


def get_threads() -> int:
    """
    Gets the amount of threads to use for example when writing to a file with MoviePy.

    Returns:
        threads (int): Amount of threads
    """
    return int(load_config().get("threads", 2))
    
def get_zip_url() -> str:
    """
    Gets the URL to the zip file containing the songs.

    Returns:
        url (str): The URL to the zip file
    """
    return get_config_value("zip_url", "")

def get_is_for_kids() -> bool:
    """
    Gets the is for kids flag from the config file.

    Returns:
        is_for_kids (bool): The is for kids flag
    """
    return bool(get_config_value("is_for_kids", False))

def get_google_maps_scraper_zip_url() -> str:
    """
    Gets the URL to the zip file containing the Google Maps scraper.

    Returns:
        url (str): The URL to the zip file
    """
    return get_config_value("google_maps_scraper", "")

def get_google_maps_scraper_niche() -> str:
    """
    Gets the niche for the Google Maps scraper.

    Returns:
        niche (str): The niche
    """
    return get_config_value("google_maps_scraper_niche", "")

def get_scraper_timeout() -> int:
    """
    Gets the timeout for the scraper.

    Returns:
        timeout (int): The timeout
    """
    return get_config_value("scraper_timeout", 300) or 300

def get_outreach_message_subject() -> str:
    """
    Gets the outreach message subject.

    Returns:
        subject (str): The outreach message subject
    """
    return get_config_value("outreach_message_subject", "")
    
def get_outreach_message_body_file() -> str:
    """
    Gets the outreach message body file.

    Returns:
        file (str): The outreach message body file
    """
    return get_config_value("outreach_message_body_file", "")

def get_tts_voice() -> str:
    """
    Gets the TTS voice from the config file.

    Returns:
        voice (str): The TTS voice
    """
    return get_config_value("tts_voice", "Jasper")


def get_tts_provider() -> str:
    """
    Gets the configured TTS provider.

    Returns:
        provider (str): The TTS provider. "kitten" uses KittenTTS, "silent" writes a valid silent WAV for smoke tests.
    """
    return get_config_value("tts_provider", "kitten")

def get_assemblyai_api_key() -> str:
    """
    Gets the AssemblyAI API key.

    Returns:
        key (str): The AssemblyAI API key
    """
    return get_config_value("assembly_ai_api_key", "")

def get_stt_provider() -> str:
    """
    Gets the configured STT provider.

    Returns:
        provider (str): The STT provider
    """
    return get_config_value("stt_provider", "local_whisper")

def get_whisper_model() -> str:
    """
    Gets the local Whisper model name.

    Returns:
        model (str): Whisper model name
    """
    return get_config_value("whisper_model", "base")

def get_whisper_device() -> str:
    """
    Gets the target device for Whisper inference.

    Returns:
        device (str): Whisper device
    """
    return get_config_value("whisper_device", "auto")

def get_whisper_compute_type() -> str:
    """
    Gets the compute type for Whisper inference.

    Returns:
        compute_type (str): Whisper compute type
    """
    return get_config_value("whisper_compute_type", "int8")
    
def equalize_subtitles(srt_path: str, max_chars: int = 10) -> None:
    """
    Equalizes the subtitles in a SRT file.

    Args:
        srt_path (str): The path to the SRT file
        max_chars (int): The maximum amount of characters in a subtitle

    Returns:
        None
    """
    import srt_equalizer

    srt_equalizer.equalize_srt_file(srt_path, srt_path, max_chars)
    
def get_font() -> str:
    """
    Gets the font from the config file.

    Returns:
        font (str): The font
    """
    return load_config().get("font", "bold_font.ttf")

def get_fonts_dir() -> str:
    """
    Gets the fonts directory.

    Returns:
        dir (str): The fonts directory
    """
    return os.path.join(ROOT_DIR, "fonts")

def get_imagemagick_path() -> str:
    """
    Gets the path to ImageMagick.

    Returns:
        path (str): The path to ImageMagick
    """
    return get_config_value("imagemagick_path", "")

def get_script_sentence_length() -> int:
    """
    Gets the forced script's sentence length.
    In case there is no sentence length in config, returns 4 when none

    Returns:
        length (int): Length of script's sentence
    """
    config_json = load_config()
    if config_json.get("script_sentence_length") is not None:
        return config_json["script_sentence_length"]
    return 4

def get_news_pipeline_config() -> dict:
    """
    Gets the tech-news collection/ranking pipeline configuration.

    Returns:
        config (dict): Sanitized news pipeline configuration
    """
    defaults = {
        "enabled": True,
        "max_article_age_hours": 48,
        "max_candidates_per_source": 4,
        "max_selected_articles": 8,
        "use_llm_scoring": True,
        "sources": [
            "theverge",
            "zdnet_korea",
            "bloter",
            "etnews",
            "engadget",
            "ars_technica",
            "wired",
            "mit_technology_review",
            "apple_newsroom",
            "google_keyword",
            "microsoft_source",
            "samsung_newsroom",
            "samsung_mobile_press",
            "openai_news",
            "anthropic_news",
            "google_deepmind_blog",
            "google_news_technology",
            "ifixit_news",
            "toms_hardware",
            "meeco_news",
            "quasarzone_hardware_news",
            "quasarzone_mobile_news",
            "geeknews",
            "newstap",
            "the_edit",
        ],
        "priority_keywords": [
            "samsung",
            "galaxy",
            "battery",
            "display",
            "udc",
            "출시",
            "공개",
            "발표",
            "반도체",
            "디스플레이",
            "배터리",
        ],
        "scoring_weights": {
            "public_interest": 0.35,
            "realism": 0.30,
            "llm": 0.25,
            "keyword": 0.10,
        },
    }
    supported_sources = set(defaults["sources"])

    config_json = load_config()

    raw_config = config_json.get("news_pipeline", {})
    if not isinstance(raw_config, dict):
        raw_config = {}

    raw_sources = raw_config.get("sources", defaults["sources"])
    sources = []
    if isinstance(raw_sources, list):
        for source in raw_sources:
            normalized_source = str(source).strip()
            if (
                normalized_source in supported_sources
                and normalized_source not in sources
            ):
                sources.append(normalized_source)
    if not sources:
        sources = defaults["sources"].copy()

    raw_weights = raw_config.get("scoring_weights", {})
    if not isinstance(raw_weights, dict):
        raw_weights = {}
    scoring_weights = defaults["scoring_weights"].copy()
    for key in scoring_weights:
        try:
            scoring_weights[key] = float(raw_weights.get(key, scoring_weights[key]))
        except (TypeError, ValueError):
            pass

    def read_int(key: str) -> int:
        try:
            return max(1, int(raw_config.get(key, defaults[key])))
        except (TypeError, ValueError):
            return defaults[key]

    raw_priority_keywords = raw_config.get(
        "priority_keywords",
        defaults["priority_keywords"],
    )
    if not isinstance(raw_priority_keywords, list):
        raw_priority_keywords = defaults["priority_keywords"].copy()

    return {
        "enabled": bool(raw_config.get("enabled", defaults["enabled"])),
        "max_article_age_hours": read_int("max_article_age_hours"),
        "max_candidates_per_source": read_int("max_candidates_per_source"),
        "max_selected_articles": read_int("max_selected_articles"),
        "use_llm_scoring": bool(
            raw_config.get("use_llm_scoring", defaults["use_llm_scoring"])
        ),
        "sources": sources,
        "priority_keywords": raw_priority_keywords,
        "scoring_weights": scoring_weights,
    }

def get_youtube_channel_config() -> dict:
    """Return YouTube channel settings from env first, then config.json.

    Public repositories should keep channel-specific identifiers out of source.
    Set these in .env/config.json for local upload automation:
    - YOUTUBE_CHANNEL_SLUG or youtube_channel.slug
    - YOUTUBE_CHANNEL_NAME or youtube_channel.name
    - YOUTUBE_CHANNEL_ID or youtube_channel.id
    """
    config = load_config()
    raw_config = config.get("youtube_channel", {})
    if not isinstance(raw_config, dict):
        raw_config = {}

    def read_setting(env_name: str, config_key: str, default: str = "") -> str:
        return (
            get_env_var(env_name, "").strip()
            or str(raw_config.get(config_key, "") or "").strip()
            or default
        )

    return {
        "slug": read_setting("YOUTUBE_CHANNEL_SLUG", "slug", "youtube-channel"),
        "name": read_setting("YOUTUBE_CHANNEL_NAME", "name", ""),
        "id": read_setting("YOUTUBE_CHANNEL_ID", "id", ""),
    }


def get_post_bridge_config() -> dict:
    """
    Gets the Post Bridge configuration with safe defaults.

    Returns:
        config (dict): Sanitized Post Bridge configuration
    """
    defaults = {
        "enabled": False,
        "api_key": "",
        "platforms": ["tiktok", "instagram"],
        "account_ids": [],
        "auto_crosspost": False,
    }
    supported_platforms = {"tiktok", "instagram"}

    config_json = load_config()
    raw_config = config_json.get("post_bridge", {})
    if not isinstance(raw_config, dict):
        raw_config = {}

    raw_platforms = raw_config.get("platforms")
    normalized_platforms = []
    seen_platforms = set()

    if raw_platforms is None:
        normalized_platforms = defaults["platforms"].copy()
    elif isinstance(raw_platforms, list):
        for platform in raw_platforms:
            normalized_platform = str(platform).strip().lower()
            if (
                normalized_platform in supported_platforms
                and normalized_platform not in seen_platforms
            ):
                normalized_platforms.append(normalized_platform)
                seen_platforms.add(normalized_platform)
    else:
        normalized_platforms = []

    raw_account_ids = raw_config.get("account_ids", defaults["account_ids"])
    normalized_account_ids = []
    if isinstance(raw_account_ids, list):
        for account_id in raw_account_ids:
            try:
                normalized_account_ids.append(int(account_id))
            except (TypeError, ValueError):
                continue

    api_key = str(raw_config.get("api_key", "")).strip()
    if not api_key:
        api_key = os.environ.get("POST_BRIDGE_API_KEY", "").strip()

    return {
        "enabled": bool(raw_config.get("enabled", defaults["enabled"])),
        "api_key": api_key,
        "platforms": normalized_platforms,
        "account_ids": normalized_account_ids,
        "auto_crosspost": bool(
            raw_config.get("auto_crosspost", defaults["auto_crosspost"])
        ),
    }
