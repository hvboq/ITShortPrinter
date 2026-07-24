import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "scripts" / "preflight_local.py"


class PreflightLocalTests(unittest.TestCase):
    def test_hermes_image_provider_skips_gemini_key_requirement(self) -> None:
        source = PREFLIGHT.read_text(encoding="utf-8")

        self.assertIn("image_provider = get_image_provider().lower()", source)
        self.assertIn('if image_provider == "hermes"', source)
        self.assertIn('Hermes image provider selected', source)

    def test_placeholder_image_provider_skips_external_api_checks(self) -> None:
        source = PREFLIGHT.read_text(encoding="utf-8")

        self.assertIn('elif image_provider == "placeholder"', source)
        self.assertIn('image_provider in {"hermes", "placeholder"}', source)

    def test_hermes_text_provider_checks_hermes_cli_instead_of_ollama(self) -> None:
        source = PREFLIGHT.read_text(encoding="utf-8")

        self.assertIn("text_provider = get_text_provider().lower()", source)
        self.assertIn("base = get_ollama_base_url()", source)
        self.assertIn('if text_provider == "hermes"', source)
        self.assertIn('Hermes text provider selected', source)
        self.assertIn('["hermes", "chat", "-q"', source)
        self.assertIn('"--provider", hermes_provider', source)


if __name__ == "__main__":
    unittest.main()
