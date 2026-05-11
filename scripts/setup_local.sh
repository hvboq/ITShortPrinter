#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[setup] Root: $ROOT_DIR"

REQUIRED_PYTHON_VERSION="${REQUIRED_PYTHON_VERSION:-$(tr -d '[:space:]' < .python-version 2>/dev/null || echo 3.12)}"
VENV_DIR="${VENV_DIR:-venv}"
VENV_PATH="${ROOT_DIR}/${VENV_DIR}"
PYTHON_BIN="${VENV_PATH}/bin/python"

python_minor_version() {
  "$1" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
}

resolve_python_candidate() {
  local candidate="$1"
  local resolved=""

  if [[ -x "$candidate" ]]; then
    resolved="$candidate"
  else
    resolved="$(command -v "$candidate" 2>/dev/null || true)"
  fi

  if [[ -n "$resolved" && "$(python_minor_version "$resolved" 2>/dev/null || true)" == "$REQUIRED_PYTHON_VERSION" ]]; then
    echo "$resolved"
    return 0
  fi

  return 1
}

find_required_python() {
  local candidates=()

  if [[ -n "${PYTHON:-}" ]]; then
    candidates+=("$PYTHON")
  fi

  candidates+=("python${REQUIRED_PYTHON_VERSION}" "python3")

  if command -v pyenv >/dev/null 2>&1; then
    local pyenv_python
    pyenv_python="$(PYENV_VERSION="$REQUIRED_PYTHON_VERSION" pyenv which python 2>/dev/null || true)"
    if [[ -n "$pyenv_python" ]]; then
      candidates+=("$pyenv_python")
    fi
  fi

  local candidate
  for candidate in "${candidates[@]}"; do
    resolve_python_candidate "$candidate" && return 0
  done

  return 1
}

ensure_compatible_venv() {
  if [[ ! -x "$PYTHON_BIN" ]]; then
    return 0
  fi

  local existing_version
  existing_version="$(python_minor_version "$PYTHON_BIN" 2>/dev/null || true)"
  if [[ "$existing_version" == "$REQUIRED_PYTHON_VERSION" ]]; then
    return 0
  fi

  if [[ "${RECREATE_VENV:-0}" == "1" ]]; then
    echo "[setup] Existing ${VENV_DIR}/ uses Python ${existing_version:-unknown}; recreating for ${REQUIRED_PYTHON_VERSION}."
    rm -rf "$VENV_PATH"
    return 0
  fi

  echo "[setup] ERROR: Existing ${VENV_DIR}/ uses Python ${existing_version:-unknown}, but this project requires Python ${REQUIRED_PYTHON_VERSION}."
  echo "[setup] Run with RECREATE_VENV=1 to rebuild it, or set VENV_DIR to a different path."
  exit 1
}

if [[ ! -f "config.json" ]]; then
  cp config.example.json config.json
  echo "[setup] Created config.json from config.example.json"
fi

ensure_compatible_venv

if [[ ! -x "$PYTHON_BIN" ]]; then
  BASE_PYTHON="$(find_required_python || true)"
  if [[ -z "$BASE_PYTHON" ]]; then
    echo "[setup] ERROR: Python ${REQUIRED_PYTHON_VERSION} was not found."
    echo "[setup] Install Python ${REQUIRED_PYTHON_VERSION} first, or set PYTHON=/path/to/python${REQUIRED_PYTHON_VERSION}."
    exit 1
  fi

  "$BASE_PYTHON" -m venv "$VENV_DIR"
  echo "[setup] Created virtual environment at ${VENV_DIR}/ with $("$PYTHON_BIN" --version)"
fi

"$PYTHON_BIN" -m ensurepip --upgrade >/dev/null 2>&1 || true
"$PYTHON_BIN" -m pip install --upgrade pip setuptools wheel
"$PYTHON_BIN" -m pip install -r requirements.txt

MAGICK_PATH="$(command -v magick || true)"
if [[ -z "$MAGICK_PATH" ]]; then
  MAGICK_PATH="$(command -v convert || true)"
fi

FIREFOX_PROFILE=""
if [[ -d "$HOME/Library/Application Support/Firefox/Profiles" ]]; then
  FIREFOX_PROFILE="$(find "$HOME/Library/Application Support/Firefox/Profiles" -maxdepth 1 -type d -name "*default-release*" | head -n 1 || true)"
  if [[ -z "$FIREFOX_PROFILE" ]]; then
    FIREFOX_PROFILE="$(find "$HOME/Library/Application Support/Firefox/Profiles" -maxdepth 1 -type d | tail -n +2 | head -n 1 || true)"
  fi
fi

OLLAMA_MODELS_JSON="$(curl -sS http://127.0.0.1:11434/api/tags || true)"

MAGICK_PATH="$MAGICK_PATH" FIREFOX_PROFILE="$FIREFOX_PROFILE" "$PYTHON_BIN" - <<'PY'
import json
import os
import subprocess

ROOT_DIR = os.getcwd()
cfg_path = os.path.join(ROOT_DIR, "config.json")

with open(cfg_path, "r", encoding="utf-8") as f:
    cfg = json.load(f)

# Set defaults per service without overriding explicit user choices.
cfg.setdefault("llm_provider", "local_ollama")
cfg.setdefault("image_provider", "local_automatic1111")
cfg.setdefault("stt_provider", "local_whisper")

cfg.setdefault("ollama_base_url", "http://127.0.0.1:11434")
cfg.setdefault("automatic1111_base_url", "http://127.0.0.1:7860")
cfg.setdefault("cloudflare_worker_url", "")
cfg.setdefault("whisper_model", "base")
cfg.setdefault("whisper_device", "auto")
cfg.setdefault("whisper_compute_type", "int8")

magick_path = os.environ.get("MAGICK_PATH", "")
if magick_path:
    cfg["imagemagick_path"] = magick_path

firefox_profile = os.environ.get("FIREFOX_PROFILE", "")
if firefox_profile and not cfg.get("firefox_profile"):
    cfg["firefox_profile"] = firefox_profile

# Pick a reasonable installed Ollama model.
ollama_model = cfg.get("ollama_model", "llama3.2:3b")
installed = []
try:
    out = subprocess.check_output(
        ["curl", "-sS", "http://127.0.0.1:11434/api/tags"],
        text=True,
    )
    payload = json.loads(out)
    installed = [m.get("name") for m in payload.get("models", []) if m.get("name")]
except Exception:
    installed = []

if installed:
    preferred = [
        "glm-4.7-flash:latest",
        "qwen3:14b",
        "phi4:latest",
        "phi4:14b",
        "gpt-oss:20b",
        "deepseek-r1:32b",
    ]
    selected = None
    for candidate in preferred:
        if candidate in installed:
            selected = candidate
            break

    if selected is None:
        selected = installed[0]

    if ollama_model not in installed or ollama_model != selected:
        cfg["ollama_model"] = selected

with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")

print(f"[setup] Updated {cfg_path}")
print(f"[setup] llm_provider={cfg.get('llm_provider')} model={cfg.get('ollama_model')}")
print(f"[setup] image_provider={cfg.get('image_provider')}")
print(f"[setup] stt_provider={cfg.get('stt_provider')}")
PY

echo "[setup] Running local preflight..."
"$PYTHON_BIN" scripts/preflight_local.py || true

echo ""
echo "[setup] Done."
echo "[setup] Start app with: source ${VENV_DIR}/bin/activate && python src/main.py"
