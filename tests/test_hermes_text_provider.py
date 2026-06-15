import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class HermesTextProviderTests(unittest.TestCase):
    def test_hermes_model_routes_generation_through_hermes_cli(self):
        import llm_provider

        with patch("llm_provider._run_hermes_chat", return_value="  대본 결과  ") as run_hermes:
            result = llm_provider.generate_text("프롬프트", model_name="hermes:gpt-5.5")

        self.assertEqual(result, "대본 결과")
        run_hermes.assert_called_once_with("프롬프트", model_name="gpt-5.5")

    def test_hermes_cli_command_uses_quiet_single_query_with_model(self):
        import llm_provider

        completed = type(
            "Completed",
            (),
            {"returncode": 0, "stdout": "응답\n", "stderr": ""},
        )()

        with patch("llm_provider.subprocess.run", return_value=completed) as run:
            result = llm_provider._run_hermes_chat("질문", model_name="gpt-5.5")

        self.assertEqual(result, "응답")
        args = run.call_args.args[0]
        self.assertEqual(args[:3], ["hermes", "chat", "-q"])
        self.assertIn("--quiet", args)
        self.assertIn("--model", args)
        self.assertIn("gpt-5.5", args)
        self.assertEqual(run.call_args.kwargs["input"], None)
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")

    def test_hermes_cli_command_uses_configured_provider(self):
        import llm_provider

        completed = type(
            "Completed",
            (),
            {"returncode": 0, "stdout": "응답\n", "stderr": ""},
        )()

        with patch("llm_provider.get_hermes_provider", return_value="openai-codex"), patch(
            "llm_provider.subprocess.run", return_value=completed
        ) as run:
            llm_provider._run_hermes_chat("질문", model_name="gpt-5.5")

        args = run.call_args.args[0]
        self.assertIn("--provider", args)
        self.assertIn("openai-codex", args)

    def test_text_provider_defaults_can_be_configured_to_hermes(self):
        import config

        with patch("config.load_config", return_value={"text_provider": "hermes", "hermes_model": "gpt-5.5", "hermes_provider": "openai-codex"}):
            self.assertEqual(config.get_text_provider(), "hermes")
            self.assertEqual(config.get_hermes_model(), "gpt-5.5")
            self.assertEqual(config.get_hermes_provider(), "openai-codex")
            self.assertEqual(config.get_default_text_model(), "hermes:gpt-5.5")


if __name__ == "__main__":
    unittest.main()
