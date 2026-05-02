import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class ConfigOptionalDependencyTests(unittest.TestCase):
    def test_config_import_does_not_require_srt_equalizer_until_equalizing_subtitles(self):
        sys.modules.pop("config", None)
        sys.modules.pop("srt_equalizer", None)

        real_import = __import__

        def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "srt_equalizer":
                raise ModuleNotFoundError("No module named 'srt_equalizer'")
            return real_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=blocked_import):
            config = importlib.import_module("config")

        self.assertTrue(hasattr(config, "get_ollama_base_url"))


if __name__ == "__main__":
    unittest.main()
