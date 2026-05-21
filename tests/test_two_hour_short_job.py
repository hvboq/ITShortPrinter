from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "scripts" / "run_two_hour_short_job.py"
WINDOWS_WRAPPER = ROOT / "scripts" / "run_two_hour_short_job_windows.ps1"
UNLISTED_UPLOAD = ROOT / "scripts" / "upload_top5_shorts.py"


class TwoHourShortJobTests(unittest.TestCase):
    def test_two_hour_job_entrypoint_exists_and_has_safe_operational_controls(self) -> None:
        source = JOB.read_text(encoding="utf-8")
        tree = ast.parse(source)
        function_names = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        }

        self.assertIn("main", function_names)
        self.assertIn("acquire_lock", function_names)
        self.assertIn("release_lock", function_names)
        self.assertIn("select_next_article", function_names)
        self.assertIn("write_single_item_manifest", function_names)
        self.assertIn("run_job", function_names)
        self.assertIn("SHORTS_JOB_VISIBILITY", source)
        self.assertIn("SHORTS_JOB_DRY_RUN", source)
        self.assertIn("SHORTS_JOB_LOCK_TTL_MINUTES", source)
        self.assertIn("START_RANK", source)
        self.assertIn("END_RANK", source)
        self.assertIn("upload_top5_public_shorts", source)

    def test_windows_wrapper_runs_repo_venv_job_and_preserves_exit_code(self) -> None:
        source = WINDOWS_WRAPPER.read_text(encoding="utf-8")

        self.assertIn("run_two_hour_short_job.py", source)
        self.assertIn(".\\venv\\Scripts\\python.exe", source)
        self.assertIn("Set-Location", source)
        self.assertIn("exit $LASTEXITCODE", source)
        self.assertIn("SHORTS_JOB_VISIBILITY", source)
    def test_unlisted_upload_script_accepts_single_job_manifest_overrides(self) -> None:
        source = UNLISTED_UPLOAD.read_text(encoding="utf-8")

        self.assertIn("UPLOAD_SOURCE_MANIFEST", source)
        self.assertIn("UPLOAD_OUTPUT_MANIFEST", source)
        self.assertIn("UPLOAD_SCREEN_DIR", source)
        self.assertIn("START_RANK", source)
        self.assertIn("END_RANK", source)


if __name__ == "__main__":
    unittest.main()
