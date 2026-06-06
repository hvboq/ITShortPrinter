from __future__ import annotations

import ast
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "scripts" / "run_two_hour_short_job.py"
WINDOWS_WRAPPER = ROOT / "scripts" / "run_two_hour_short_job_windows.ps1"
PRODUCT_JOB = ROOT / "scripts" / "run_product_launch_short_job.py"
UNLISTED_UPLOAD = ROOT / "scripts" / "upload_top5_shorts.py"


def load_job_module():
    spec = importlib.util.spec_from_file_location("run_two_hour_short_job_test", JOB)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        self.assertIn("PRODUCT_LAUNCH_SOURCE_MODE", source)
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
    def test_product_launch_job_entrypoint_forces_dedicated_topic(self) -> None:
        source = PRODUCT_JOB.read_text(encoding="utf-8")

        self.assertIn('os.environ["SHORTS_JOB_TOPIC"] = "product_launch"', source)
        self.assertIn('os.environ.setdefault("NEWS_LIMIT", "120")', source)
        self.assertIn("run_two_hour_short_job", source)

    def test_unlisted_upload_script_accepts_single_job_manifest_overrides(self) -> None:
        source = UNLISTED_UPLOAD.read_text(encoding="utf-8")

        self.assertIn("UPLOAD_SOURCE_MANIFEST", source)
        self.assertIn("UPLOAD_OUTPUT_MANIFEST", source)
        self.assertIn("UPLOAD_SCREEN_DIR", source)
        self.assertIn("START_RANK", source)
        self.assertIn("END_RANK", source)

    def test_product_launch_topic_filter_accepts_launch_and_rejects_market_context(self) -> None:
        job = load_job_module()

        launch_article = {
            "title": "Samsung unveils Galaxy Book 5 laptop for Korea launch",
            "raw_excerpt": "The new product is officially announced with launch details.",
            "event_type": "",
        }
        market_article = {
            "title": "Samsung reports stronger quarterly semiconductor earnings",
            "raw_excerpt": "Management says demand is improving.",
            "event_type": "market_context",
        }

        self.assertTrue(job.matches_requested_topic(launch_article, "product_launch"))
        self.assertFalse(job.matches_requested_topic(market_article, "product_launch"))
        self.assertTrue(job.matches_requested_topic(market_article, ""))

    def test_product_launch_topic_rejects_software_release_wording(self) -> None:
        job = load_job_module()
        software_article = {
            "title": "아이폰도 이제 AI이미지 생성 되나.. 9일 새로운 시리 출시",
            "raw_excerpt": "새로운 기능과 앱 업데이트가 제공된다.",
            "event_type": "software_update",
        }
        availability_article = {
            "title": "삼성전자 갤럭시 S26 시리즈 사전 판매 시작",
            "raw_excerpt": "국내 출시 일정과 예약 판매 혜택을 발표했다.",
            "event_type": "price_availability",
        }

        self.assertFalse(job.matches_requested_topic(software_article, "product_launch"))
        self.assertTrue(job.matches_requested_topic(availability_article, "product_launch"))

    def test_select_next_article_can_limit_candidates_to_product_launch_topic(self) -> None:
        job = load_job_module()
        articles = [
            {
                "title": "Intel market share report improves",
                "url": "https://example.com/market",
                "event_type": "market_context",
                "shorts_score": 99,
                "topic_bucket": "pc_chip_device",
            },
            {
                "title": "Logitech launches new MX keyboard in Korea",
                "url": "https://example.com/launch",
                "event_type": "product_launch",
                "shorts_score": 80,
                "topic_bucket": "peripheral_wearable_audio",
            },
        ]

        with patch.object(job, "collect_product_launch_news", return_value=articles), patch.object(job, "load_upload_history", return_value=[]):
            selected = job.select_next_article(limit=10, topic="product_launch")

        self.assertEqual(selected["url"], "https://example.com/launch")

    def test_general_topic_uses_general_news_collector(self) -> None:
        job = load_job_module()
        articles = [
            {
                "title": "Intel market share report improves",
                "url": "https://example.com/market",
                "event_type": "market_context",
                "shorts_score": 99,
            }
        ]

        with patch.object(job, "collect_ranked_news", return_value=articles) as general, patch.object(
            job, "collect_product_launch_news", return_value=[]
        ) as product, patch.object(job, "load_upload_history", return_value=[]):
            selected = job.select_next_article(limit=10, topic="")

        self.assertEqual(selected["url"], "https://example.com/market")
        general.assert_called_once_with(limit=10)
        product.assert_not_called()

    def test_product_launch_topic_uses_dedicated_news_collector(self) -> None:
        job = load_job_module()
        articles = [
            {
                "title": "Logitech launches new MX keyboard in Korea",
                "url": "https://example.com/launch",
                "event_type": "product_launch",
                "shorts_score": 80,
            }
        ]

        with patch.object(job, "collect_product_launch_news", return_value=articles) as product, patch.object(
            job, "collect_ranked_news", return_value=[]
        ) as general, patch.object(job, "load_upload_history", return_value=[]):
            selected = job.select_next_article(limit=10, topic="product_launch")

        self.assertEqual(selected["url"], "https://example.com/launch")
        product.assert_called_once_with(limit=10)
        general.assert_not_called()


if __name__ == "__main__":
    unittest.main()
