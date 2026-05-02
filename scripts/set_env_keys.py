#!/usr/bin/env python3
"""Safely write MoneyPrinterV2 local API keys to .env without echoing input."""

from __future__ import annotations

import getpass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def ask_secret(name: str, required: bool = False) -> str:
    while True:
        value = getpass.getpass(f"{name} (input hidden, blank to skip): ").strip()
        if value or not required:
            return value
        print(f"{name} is required.")


def main() -> None:
    google = ask_secret("GOOGLE_API_KEY", required=True)
    openai = ask_secret("OPENAI_API_KEY", required=False)
    gemini = ask_secret("GEMINI_API_KEY", required=False)

    lines = [
        "# Local secrets for MoneyPrinterV2. Do not commit this file.",
        f"GOOGLE_API_KEY={google}",
        f"GEMINI_API_KEY={gemini}",
        f"OPENAI_API_KEY={openai}",
        "IMAGE_PROVIDER=gemini",
        "",
    ]
    ENV_PATH.write_text("\n".join(lines), encoding="utf-8")
    ENV_PATH.chmod(0o600)
    print(f"Wrote {ENV_PATH} with permissions 600.")
    print("Key values were not printed.")


if __name__ == "__main__":
    main()
