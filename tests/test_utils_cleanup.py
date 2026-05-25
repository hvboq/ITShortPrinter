import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class UtilsCleanupTests(unittest.TestCase):
    def test_rem_temp_files_preserves_operational_outputs_and_directories(self):
        import utils

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mp_dir = root / ".mp"
            mp_dir.mkdir()
            (mp_dir / "batch_top5").mkdir()
            (mp_dir / "batch_top5" / "manifest.json").write_text(
                "[]", encoding="utf-8"
            )
            (mp_dir / "news.json").write_text(
                json.dumps({"latest_candidates": []}), encoding="utf-8"
            )
            (mp_dir / "generated.mp4").write_bytes(b"video")
            (mp_dir / "subtitle.srt").write_text("1\n", encoding="utf-8")

            with patch.object(utils, "ROOT_DIR", str(root)):
                utils.rem_temp_files()

            self.assertTrue((mp_dir / "batch_top5").is_dir())
            self.assertTrue((mp_dir / "batch_top5" / "manifest.json").exists())
            self.assertTrue((mp_dir / "news.json").exists())
            self.assertFalse((mp_dir / "generated.mp4").exists())
            self.assertFalse((mp_dir / "subtitle.srt").exists())


if __name__ == "__main__":
    unittest.main()
