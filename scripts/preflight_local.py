#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from typing import Tuple

try:
    import requests
except ModuleNotFoundError:
    requests = None


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT_DIR, "config.json")


def ok(msg: str) -> None:
    print(f"[OK] {msg}")


def warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def fail(msg: str) -> None:
    print(f"[FAIL] {msg}")


def check_url(url: str, timeout: int = 3) -> Tuple[bool, str]:
    if requests is None:
        return False, "requests is not installed"

    try:
        response = requests.get(url, timeout=timeout)
        return True, f"HTTP {response.status_code}"
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    if not os.path.exists(CONFIG_PATH):
        fail(f"Missing config file: {CONFIG_PATH}")
        return 1

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    failures = 0

    stt_provider = str(cfg.get("stt_provider", "local_whisper")).lower()
    image_provider = str(cfg.get("image_provider", "gemini")).lower()
    text_provider = str(cfg.get("text_provider", "ollama")).lower()
    configured_text_model = str(cfg.get("ollama_model", "")).strip()
    hermes_model = str(cfg.get("hermes_model", "gpt-5.5")).strip() or "gpt-5.5"
    hermes_provider = str(cfg.get("hermes_provider", "")).strip() or os.environ.get("HERMES_TEXT_PROVIDER", "").strip()
    using_gemini_text = configured_text_model.lower().startswith("gemini")

    ok(f"stt_provider={stt_provider}")

    imagemagick_path = cfg.get("imagemagick_path", "")
    if imagemagick_path and os.path.exists(imagemagick_path):
        ok(f"imagemagick_path exists: {imagemagick_path}")
    else:
        warn(
            "imagemagick_path is not set to a valid executable path. "
            "MoviePy subtitle rendering may fail."
        )

    firefox_profile = cfg.get("firefox_profile", "")
    if firefox_profile:
        if os.path.isdir(firefox_profile):
            ok(f"firefox_profile exists: {firefox_profile}")
        else:
            warn(f"firefox_profile does not exist: {firefox_profile}")
    else:
        warn("firefox_profile is empty. Twitter/YouTube automation requires this.")

    # Text generation provider
    if text_provider == "hermes":
        try:
            command = ["hermes", "chat", "-q", "Reply with OK only.", "--quiet", "--model", hermes_model]
            if hermes_provider:
                command.extend(["--provider", hermes_provider])

            completed = subprocess.run(
                command,
                input=None,
                capture_output=True,
                encoding="utf-8",
                timeout=90,
                check=False,
            )
            if completed.returncode == 0 and completed.stdout.strip():
                ok(f"Hermes text provider selected; Hermes CLI responded with model {hermes_model}")
            else:
                detail = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
                fail(f"Hermes text provider selected but Hermes CLI failed: {detail}")
                failures += 1
        except Exception as exc:
            fail(f"Hermes text provider selected but Hermes CLI could not run: {exc}")
            failures += 1
    elif using_gemini_text:
        ok(f"text model uses Google Gemini: {configured_text_model}")
    else:
        base = str(cfg.get("ollama_base_url", "http://127.0.0.1:11434")).rstrip("/")
        reachable, detail = check_url(f"{base}/api/tags")
        if not reachable:
            fail(f"Ollama is not reachable at {base}: {detail}")
            failures += 1
        else:
            ok(f"Ollama reachable at {base}")
            try:
                tags = requests.get(f"{base}/api/tags", timeout=5).json()
                models = [m.get("name") for m in tags.get("models", [])]
                if models:
                    ok(f"Ollama models available: {', '.join(models[:10])}")
                else:
                    warn("No models found on Ollama. Pull a model first (e.g. 'ollama pull llama3.2:3b').")
            except Exception as exc:
                warn(f"Could not validate Ollama model list: {exc}")

    # Nano Banana 2 (image generation)
    api_key = cfg.get("nanobanana2_api_key", "") or os.environ.get("GEMINI_API_KEY", "")
    nb2_base = str(
        cfg.get(
            "nanobanana2_api_base_url",
            "https://generativelanguage.googleapis.com/v1beta",
        )
    ).rstrip("/")
    if image_provider == "hermes":
        ok("Hermes image provider selected; Gemini image API key is not required")
    elif api_key:
        ok("nanobanana2_api_key is set")
    else:
        fail("nanobanana2_api_key is empty (and GEMINI_API_KEY is not set)")
        failures += 1

    if image_provider == "hermes":
        ok("Skipping Nano Banana 2 reachability check for Hermes image provider")
    else:
        reachable, detail = check_url(nb2_base, timeout=8)
        if not reachable:
            warn(f"Nano Banana 2 base URL could not be reached: {detail}")
        else:
            ok(f"Nano Banana 2 base URL reachable: {nb2_base}")

    if stt_provider == "local_whisper":
        try:
            import faster_whisper  # noqa: F401

            ok("faster-whisper is installed")
        except Exception as exc:
            fail(f"faster-whisper is not importable: {exc}")
            failures += 1

    if failures:
        print("")
        print(f"Preflight completed with {failures} blocking issue(s).")
        return 1

    print("")
    print("Preflight passed. Local setup looks ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
