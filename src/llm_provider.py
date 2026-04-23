import requests

try:
    import ollama
except ImportError:
    ollama = None

from config import get_nanobanana2_api_base_url
from config import get_nanobanana2_api_key
from config import get_ollama_base_url

_selected_model: str | None = None


def _client():
    if ollama is None:
        raise RuntimeError(
            "The 'ollama' Python package is not installed. Install dependencies to use local LLM features."
        )
    return ollama.Client(host=get_ollama_base_url())


def list_models() -> list[str]:
    """
    Lists all models available on the local Ollama server.

    Returns:
        models (list[str]): Sorted list of model names.
    """
    response = _client().list()
    return sorted(m.model for m in response.models)


def select_model(model: str) -> None:
    """
    Sets the model to use for all subsequent generate_text calls.

    Args:
        model (str): An Ollama model name (must be already pulled).
    """
    global _selected_model
    _selected_model = model


def get_active_model() -> str | None:
    """
    Returns the currently selected model, or None if none has been selected.
    """
    return _selected_model


def _is_gemini_model(model_name: str | None) -> bool:
    """
    Returns True when the model should be routed to Google's Gemini API.
    """
    normalized = str(model_name or "").strip().lower()
    return normalized.startswith("gemini")


def _generate_text_with_gemini(prompt: str, model_name: str) -> str:
    """
    Generates text using the Google Generative Language API.

    Args:
        prompt (str): User prompt
        model_name (str): Gemini model name

    Returns:
        response (str): Generated text
    """
    api_key = get_nanobanana2_api_key()
    if not api_key:
        raise RuntimeError(
            "No Google API key configured. Set 'nanobanana2_api_key' or 'GEMINI_API_KEY'."
        )

    base_url = get_nanobanana2_api_base_url().rstrip("/")
    endpoint = f"{base_url}/models/{model_name}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
        },
    }

    response = requests.post(
        endpoint,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=180,
    )
    response.raise_for_status()
    body = response.json()

    candidates = body.get("candidates", [])
    for candidate in candidates:
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            text = str(part.get("text", "")).strip()
            if text:
                return text

    raise RuntimeError(f"Gemini did not return a text response. Response: {body}")


def generate_text(prompt: str, model_name: str = None) -> str:
    """
    Generates text using the local Ollama server.

    Args:
        prompt (str): User prompt
        model_name (str): Optional model name override

    Returns:
        response (str): Generated text
    """
    model = model_name or _selected_model
    if not model:
        raise RuntimeError(
            "No text model selected. Call select_model() first or pass model_name."
        )

    if _is_gemini_model(model):
        return _generate_text_with_gemini(prompt, model)

    response = _client().chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )

    return response["message"]["content"].strip()
