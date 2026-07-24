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

    def test_windows_setup_does_not_confuse_system_convert_with_imagemagick(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("Get-Command magick", content)
        self.assertNotIn("Get-Command convert", content)

    def test_windows_setup_writes_config_as_utf8_without_bom(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("System.Text.UTF8Encoding($false)", content)
        self.assertIn("[System.IO.File]::WriteAllText", content)

    def test_provider_preflight_does_not_undo_successful_dependency_setup(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("preflight found provider/config items", content)
        self.assertNotIn("exit $preflightExit", content)

    def test_recreate_venv_is_limited_to_an_unlinked_repo_child(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("VenvDir must be a direct child directory name", content)
        self.assertIn("FileAttributes]::ReparsePoint", content)
        self.assertIn("Remove-Item -Recurse -Force -LiteralPath", content)

    def test_readme_mentions_windows_setup_script(self):
        content = README_PATH.read_text(encoding="utf-8")

        self.assertIn("scripts/setup_local_windows.ps1", content)
        self.assertIn("PowerShell", content)


if __name__ == "__main__":
    unittest.main()
