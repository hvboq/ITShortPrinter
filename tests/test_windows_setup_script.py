import pathlib
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT_DIR / "scripts" / "setup_local_windows.ps1"
README_PATH = ROOT_DIR / "README.md"


class WindowsSetupScriptTests(unittest.TestCase):
    def test_windows_setup_script_exists_and_uses_windows_venv_layout(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("venv\\Scripts\\python.exe", content)
        self.assertIn("py -3.12", content)
        self.assertIn("config.example.json", content)
        self.assertIn("scripts/preflight_local.py", content)

    def test_readme_mentions_windows_setup_script(self):
        content = README_PATH.read_text(encoding="utf-8")

        self.assertIn("scripts/setup_local_windows.ps1", content)
        self.assertIn("PowerShell", content)


if __name__ == "__main__":
    unittest.main()
