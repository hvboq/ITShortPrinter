from __future__ import annotations

import base64

try:
    import requests
except ModuleNotFoundError:  # Allows pure payload/response parsing tests without optional HTTP dependency.
    requests = None


def build_gemini_image_payload(prompt: str, aspect_ratio: str = "9:16") -> dict:
    """Build a Gemini generateContent payload that asks for image output."""
    return {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": aspect_ratio},
        },
    }


def extract_gemini_image_bytes(body: dict) -> bytes | None:
    """Extract the first image bytes from Gemini generateContent response JSON."""
    for candidate in body.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            inline_data = part.get("inlineData") or part.get("inline_data")
            if not inline_data:
                continue

            mime_type = inline_data.get("mimeType") or inline_data.get("mime_type", "")
            data = inline_data.get("data")
            if data and str(mime_type).startswith("image/"):
                return base64.b64decode(data)
    return None


def generate_gemini_image_bytes(
    prompt: str,
    api_key: str,
    base_url: str,
    model: str,
    aspect_ratio: str = "9:16",
    timeout: int = 300,
) -> bytes | None:
    """Call Gemini image generation and return raw image bytes, or None if no image is returned."""
    global requests
    if requests is None:
        import requests as requests_module
        requests = requests_module

    endpoint = f"{base_url.rstrip('/')}/models/{model}:generateContent"
    response = requests.post(
        endpoint,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=build_gemini_image_payload(prompt, aspect_ratio),
        timeout=timeout,
    )
    response.raise_for_status()
    return extract_gemini_image_bytes(response.json())
