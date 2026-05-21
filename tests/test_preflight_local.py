import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "scripts" / "preflight_local.py"


class PreflightLocalTests(unittest.TestCase):
    def test_hermes_image_provider_skips_gemini_key_requirement(self) -> None:
        source = PREFLIGHT.read_text(encoding="utf-8")

        self.assertIn('image_provider = str(cfg.get("image_provider", "gemini")).lower()', source)
        self.assertIn('if image_provider == "hermes"', source)
        self.assertIn('Hermes image provider selected', source)


if __name__ == "__main__":
    unittest.main()
