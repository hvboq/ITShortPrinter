from __future__ import annotations

import ast
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "scripts" / "run_two_hour_short_job.py"
WINDOWS_WRAPPER = ROOT / "scripts" / "run_two_hour_short_job_windows.ps1"
PRODUCT_JOB = ROOT / "scripts" / "run_product_launch_short_job.py"
UNLISTED_UPLOAD = ROOT / "scripts" / "upload_top5_shorts.py"
PUBLIC_UPLOAD = ROOT / "scripts" / "upload_top5_public_shorts.py"
UNLISTED_DRAFT_PUBLISH = ROOT / "scripts" / "publish_draft_shorts.py"
PUBLIC_DRAFT_PUBLISH = ROOT / "scripts" / "publish_draft_public_shorts.py"


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
        self.assertIn("ALLOW_PUBLIC_UPLOAD", source)
        self.assertIn("SHORTS_JOB_DRY_RUN", source)
        self.assertIn("SHORTS_JOB_LOCK_TTL_MINUTES", source)
        self.assertIn("UPDATE_UPLOAD_HISTORY", source)
        self.assertIn("UPDATE_ARCHIVE_STATUS", source)
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
        self.assertIn("UPDATE_UPLOAD_HISTORY", source)
        self.assertIn("UPDATE_ARCHIVE_STATUS", source)
        self.assertIn("START_RANK", source)
        self.assertIn("END_RANK", source)

    def test_public_draft_publish_requires_explicit_opt_in(self) -> None:
        source = PUBLIC_DRAFT_PUBLISH.read_text(encoding="utf-8")

        self.assertIn("ALLOW_PUBLIC_UPLOAD", source)
        self.assertIn("YOUTUBE_CHANNEL_ID is required", source)
        self.assertIn("verify_expected_studio_channel", source)
        self.assertIn("Refusing to publish drafts publicly", source)

    def test_public_api_upload_requires_explicit_opt_in(self) -> None:
        source = PUBLIC_UPLOAD.read_text(encoding="utf-8")

        self.assertIn("ALLOW_PUBLIC_UPLOAD", source)
        self.assertIn("Refusing public upload", source)

    def test_unlisted_draft_publish_requires_channel_id(self) -> None:
        source = UNLISTED_DRAFT_PUBLISH.read_text(encoding="utf-8")

        self.assertIn("YOUTUBE_CHANNEL_ID is required", source)
        self.assertIn("verify_expected_studio_channel", source)

    def test_single_item_manifest_includes_video_review_fields(self) -> None:
        job = load_job_module()
        article = {
            "title": "Samsung launches a new AI phone",
            "url": "https://example.com/news",
            "id": 123,
            "source_name": "Example",
            "shorts_score": 91,
            "topic_bucket": "mobile_ai",
        }
        youtube = SimpleNamespace(
            metadata={"title": "갤럭시 AI 배터리 변화"},
            script=(
                "Samsung AI phone changes battery life for everyday users. "
                "The update also changes how privacy features run on device. "
                "This short explains the practical impact without hype."
            ),
            images=["one.png", "two.png", "three.png"],
            image_prompts=["prompt one", "prompt two", "prompt three"],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            from PIL import Image

            job_dir = Path(tmpdir)
            video_path = job_dir / "short.mp4"
            subtitle_path = job_dir / "captions.srt"
            subtitle_path.write_text(
                "1\n00:00:00,000 --> 00:00:20,000\n첫 번째 자막입니다.\n\n"
                "2\n00:00:20,000 --> 00:00:42,500\n두 번째 자막입니다.\n",
                encoding="utf-8",
            )
            youtube.subtitles_path = str(subtitle_path)
            image_paths = []
            for index in range(3):
                image_path = job_dir / f"visual-{index}.png"
                Image.new("RGB", (1080, 1920), color=(20 + index * 20, 30, 45)).save(image_path)
                image_paths.append(str(image_path))
            youtube.images = image_paths
            expected_frame = job_dir / "latest_review_frame.png"
            expected_frame_2 = job_dir / "latest_review_frame_2.png"
            expected_frame_3 = job_dir / "latest_review_frame_3.png"
            expected_frame_4 = job_dir / "latest_review_frame_4.png"
            expected_sheet = job_dir / "latest_review_frame_sheet.png"
            review = {
                "duration": 42.5,
                "size": [1080, 1920],
                "fps": 30.0,
                "review_file_size_bytes": 8_000_000,
                "frame_path": str(expected_frame),
                "review_frame_timestamp": 3.4,
                "review_frame_paths": [
                    str(expected_frame),
                    str(expected_frame_2),
                    str(expected_frame_3),
                    str(expected_frame_4),
                ],
                "review_frame_timestamps": [3.4, 14.875, 24.65, 34.85],
                "review_sheet_path": str(expected_sheet),
                "review_sheet_frame_count": 4,
                "review_frame_brightness": 58.2,
                "review_frame_contrast": 22.1,
                "review_frame_brightness_values": [58.2, 61.4, 55.8, 59.0],
                "review_frame_contrast_values": [22.1, 24.5, 20.3, 23.4],
                "review_frame_center_brightness": 64.8,
                "review_frame_center_contrast": 18.6,
                "review_frame_center_brightness_values": [64.8, 67.2, 63.5, 65.0],
                "review_frame_center_contrast_values": [18.6, 20.1, 17.4, 19.2],
                "review_title_frame_count": 1,
                "review_frame_title_contrast": 36.2,
                "review_frame_title_dark_ratio": 0.22,
                "review_frame_title_bright_ratio": 0.018,
                "review_frame_title_contrast_values": [36.2, None, None, None],
                "review_frame_title_dark_ratio_values": [0.22, None, None, None],
                "review_frame_title_bright_ratio_values": [0.018, None, None, None],
                "review_subtitle_frame_count": 4,
                "review_frame_caption_contrast": 42.4,
                "review_frame_caption_dark_ratio": 0.18,
                "review_frame_caption_bright_ratio": 0.025,
                "review_frame_caption_contrast_values": [42.4, 44.8, 43.1, 42.9],
                "review_frame_caption_dark_ratio_values": [0.18, 0.2, 0.19, 0.18],
                "review_frame_caption_bright_ratio_values": [0.025, 0.03, 0.027, 0.026],
                "review_frame_motion_scores": [12.4, 18.9, 11.6],
                "review_frame_average_motion_score": 14.3,
                "review_audio_peak": 0.72,
                "review_audio_rms": 0.19,
                "review_warnings": [],
                "review_quality_pass": True,
                "review_archive_status": "generated",
                "used_temp_copy": False,
            }

            with patch.object(job, "JOB_DIR", job_dir), patch.object(
                job, "LATEST_MANIFEST", job_dir / "latest_manifest.json"
            ), patch.object(job, "extract_video_review_frame", return_value=review) as extract:
                manifest_path = job.write_single_item_manifest(article, str(video_path), youtube)

            extract.assert_called_once_with(
                str(video_path.resolve()),
                expected_frame,
                subtitle_path=str(subtitle_path),
                title_overlay_expected=True,
            )
            data = json.loads(manifest_path.read_text(encoding="utf-8"))

        item = data[0]
        self.assertEqual(item["duration"], 42.5)
        self.assertEqual(item["size"], [1080, 1920])
        self.assertEqual(item["fps"], 30.0)
        self.assertEqual(item["review_file_size_bytes"], 8_000_000)
        self.assertEqual(item["frame_path"], str(expected_frame))
        self.assertEqual(item["review_frame_timestamp"], 3.4)
        self.assertEqual(
            item["review_frame_paths"],
            [
                str(expected_frame),
                str(expected_frame_2),
                str(expected_frame_3),
                str(expected_frame_4),
            ],
        )
        self.assertEqual(item["review_frame_timestamps"], [3.4, 14.875, 24.65, 34.85])
        self.assertEqual(item["review_sheet_path"], str(expected_sheet))
        self.assertEqual(item["review_sheet_frame_count"], 4)
        self.assertEqual(item["review_frame_brightness"], 58.2)
        self.assertEqual(item["review_frame_contrast"], 22.1)
        self.assertEqual(item["review_frame_brightness_values"], [58.2, 61.4, 55.8, 59.0])
        self.assertEqual(item["review_frame_contrast_values"], [22.1, 24.5, 20.3, 23.4])
        self.assertEqual(item["review_frame_center_brightness"], 64.8)
        self.assertEqual(item["review_frame_center_contrast"], 18.6)
        self.assertEqual(item["review_frame_center_brightness_values"], [64.8, 67.2, 63.5, 65.0])
        self.assertEqual(item["review_frame_center_contrast_values"], [18.6, 20.1, 17.4, 19.2])
        self.assertEqual(item["review_title_frame_count"], 1)
        self.assertEqual(item["review_frame_title_contrast"], 36.2)
        self.assertEqual(item["review_frame_title_dark_ratio"], 0.22)
        self.assertEqual(item["review_frame_title_bright_ratio"], 0.018)
        self.assertEqual(item["review_frame_title_contrast_values"], [36.2, None, None, None])
        self.assertEqual(item["review_frame_title_dark_ratio_values"], [0.22, None, None, None])
        self.assertEqual(item["review_frame_title_bright_ratio_values"], [0.018, None, None, None])
        self.assertEqual(item["review_subtitle_frame_count"], 4)
        self.assertEqual(item["review_frame_caption_contrast"], 42.4)
        self.assertEqual(item["review_frame_caption_dark_ratio"], 0.18)
        self.assertEqual(item["review_frame_caption_bright_ratio"], 0.025)
        self.assertEqual(item["review_frame_caption_contrast_values"], [42.4, 44.8, 43.1, 42.9])
        self.assertEqual(item["review_frame_caption_dark_ratio_values"], [0.18, 0.2, 0.19, 0.18])
        self.assertEqual(item["review_frame_caption_bright_ratio_values"], [0.025, 0.03, 0.027, 0.026])
        self.assertEqual(item["review_frame_motion_scores"], [12.4, 18.9, 11.6])
        self.assertEqual(item["review_frame_average_motion_score"], 14.3)
        self.assertEqual(item["review_audio_peak"], 0.72)
        self.assertEqual(item["review_audio_rms"], 0.19)
        self.assertEqual(item["review_warnings"], [])
        self.assertTrue(item["review_quality_pass"])
        self.assertTrue(item["structure_quality_pass"])
        self.assertTrue(item["overall_quality_pass"])
        self.assertEqual(item["metadata_title"], "갤럭시 AI 배터리 변화")
        self.assertTrue(item["metadata_title_has_hangul"])
        self.assertGreater(item["metadata_title_char_count"], 0)
        self.assertEqual(item["image_count"], 3)
        self.assertTrue(item["image_file_validation_enabled"])
        self.assertEqual(item["image_file_existing_count"], 3)
        self.assertEqual(item["image_file_missing_count"], 0)
        self.assertEqual(item["image_file_unreadable_count"], 0)
        self.assertEqual(item["image_file_low_resolution_count"], 0)
        self.assertEqual(item["image_file_bad_aspect_count"], 0)
        self.assertEqual(item["image_sizes"], [[1080, 1920], [1080, 1920], [1080, 1920]])
        self.assertEqual(item["image_prompt_count"], 3)
        self.assertEqual(item["image_prompt_unique_count"], 3)
        self.assertGreaterEqual(item["visual_clip_count"], 3)
        self.assertEqual(item["subtitle_path"], str(subtitle_path))
        self.assertTrue(item["subtitle_file_exists"])
        self.assertGreater(item["subtitle_file_bytes"], 0)
        self.assertEqual(item["subtitle_entry_count"], 2)
        self.assertEqual(item["subtitle_first_start_seconds"], 0.0)
        self.assertEqual(item["subtitle_last_end_seconds"], 42.5)
        self.assertEqual(item["subtitle_coverage_ratio"], 1.0)
        self.assertEqual(item["structure_warnings"], [])
        self.assertEqual(item["review_archive_status"], "generated")
        self.assertFalse(item["review_used_temp_copy"])

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

    def test_product_launch_topic_rejects_delayed_launch_wording(self) -> None:
        job = load_job_module()
        delayed_article = {
            "title": "EU가 막았다…애플, 아이폰·아이패드용 시리 AI 출시 무기한 연기",
            "raw_excerpt": "Apple delayed the launch of its AI feature indefinitely.",
            "event_type": "price_availability",
        }

        self.assertFalse(job.matches_requested_topic(delayed_article, "product_launch"))

    def test_product_launch_topic_rejects_financial_trading_desk_launches(self) -> None:
        job = load_job_module()
        finance_article = {
            "title": "갤럭시 디지털, 기관 대상 장외 예측시장 트레이딩 데스크 출시",
            "raw_excerpt": "금융 거래 서비스를 위한 신규 데스크를 출시했다.",
            "event_type": "product_launch",
        }

        self.assertFalse(job.matches_requested_topic(finance_article, "product_launch"))

    def test_product_launch_topic_rejects_credit_card_partnership_launches(self) -> None:
        job = load_job_module()
        card_article = {
            "title": "삼성카드, 롯데홈쇼핑 제휴 카드 출시",
            "raw_excerpt": "결제금액 할인 혜택을 제공하는 신용카드 상품을 선보였다.",
            "event_type": "product_launch",
        }
        graphics_article = {
            "title": "엔비디아 RTX 5090 그래픽카드 국내 출시",
            "raw_excerpt": "새 GPU 제품의 국내 판매가 시작됐다.",
            "event_type": "product_launch",
        }

        self.assertFalse(job.matches_requested_topic(card_article, "product_launch"))
        self.assertTrue(job.matches_requested_topic(graphics_article, "product_launch"))

    def test_product_launch_topic_rejects_rumored_release_but_accepts_real_preorder(self) -> None:
        job = load_job_module()
        rumored = {
            "title": "책처럼 접는 애플 폴더블폰 출시설, 아이폰 울트라 사양 6가지",
            "raw_excerpt": "Rumored features and expected release timing.",
            "event_type": "product_launch",
        }
        preorder = {
            "title": "갤럭시 Z 트라이폴드 중국서 사전 예약 개시",
            "raw_excerpt": "새 폴더블 스마트폰의 예약 판매가 시작됐다.",
            "event_type": "certification",
        }

        self.assertFalse(job.matches_requested_topic(rumored, "product_launch"))
        self.assertTrue(job.matches_requested_topic(preorder, "product_launch"))

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

    def test_select_next_article_falls_back_to_unused_archive_candidate(self) -> None:
        job = load_job_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "archive.sqlite3"
            con = sqlite3.connect(db_path)
            con.execute(
                """
                CREATE TABLE articles (
                    id TEXT PRIMARY KEY,
                    payload_json TEXT,
                    title TEXT,
                    url TEXT,
                    canonical_url TEXT,
                    source_name TEXT,
                    shorts_score INTEGER,
                    event_type TEXT,
                    topic_bucket TEXT,
                    published_at TEXT,
                    fetched_at TEXT,
                    archived_at TEXT,
                    shorts_video_status TEXT
                )
                """
            )
            article = {
                "id": "archive-1",
                "title": "Archive GPU story",
                "url": "https://example.com/archive-gpu",
                "source_name": "archive_source",
                "shorts_score": 91,
                "event_type": "market_context",
            }
            con.execute(
                """
                INSERT INTO articles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article["id"],
                    json.dumps(article),
                    article["title"],
                    article["url"],
                    article["url"],
                    article["source_name"],
                    article["shorts_score"],
                    article["event_type"],
                    "ai_infra",
                    "2026-06-09T00:00:00Z",
                    "2026-06-09T00:00:00Z",
                    "2026-06-09T00:00:00Z",
                    "not_generated",
                ),
            )
            con.commit()
            con.close()

            live_used = {"title": "Live already used", "url": "https://example.com/live", "shorts_score": 99}
            history = [{"article_url": "https://example.com/live", "article_title": "Live already used"}]
            with patch.object(job, "ARCHIVE_DB", db_path), patch.object(
                job, "collect_ranked_news", return_value=[live_used]
            ), patch.object(job, "load_upload_history", return_value=history):
                selected = job.select_next_article(limit=10, topic="")

        self.assertEqual(selected["url"], "https://example.com/archive-gpu")
        self.assertEqual(selected["selection_source"], "archive_fallback")

    def test_release_lock_does_not_remove_new_owner_lock(self) -> None:
        job = load_job_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_file = Path(tmpdir) / "run.lock"
            job_dir = Path(tmpdir)
            with patch.object(job, "JOB_DIR", job_dir), patch.object(job, "LOCK_FILE", lock_file):
                self.assertTrue(job.acquire_lock(lock_ttl_minutes=1))
                first_owner = job._LOCK_OWNER_TOKEN
                self.assertTrue(first_owner)

                lock_file.write_text(
                    json.dumps({"pid": 999999, "started_at": job._now(), "owner_token": "new-owner"}),
                    encoding="utf-8",
                )
                job.release_lock()

                self.assertTrue(lock_file.exists())
                remaining = json.loads(lock_file.read_text(encoding="utf-8"))
                self.assertEqual(remaining["owner_token"], "new-owner")
                self.assertIsNone(job._LOCK_OWNER_TOKEN)

    def test_general_archive_fallback_skips_dedicated_product_launch_sources(self) -> None:
        job = load_job_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "archive.sqlite3"
            con = sqlite3.connect(db_path)
            con.execute(
                """
                CREATE TABLE articles (
                    id TEXT PRIMARY KEY,
                    payload_json TEXT,
                    title TEXT,
                    url TEXT,
                    canonical_url TEXT,
                    source_name TEXT,
                    shorts_score INTEGER,
                    event_type TEXT,
                    topic_bucket TEXT,
                    published_at TEXT,
                    fetched_at TEXT,
                    archived_at TEXT,
                    shorts_video_status TEXT
                )
                """
            )
            rows = [
                {
                    "id": "launch-1",
                    "title": "넷마블 신작 사전 다운로드 시작",
                    "url": "https://example.com/game-launch",
                    "source_name": "Google News KR Product Launch Query",
                    "shorts_score": 100,
                    "event_type": "product_launch",
                    "topic_bucket": "gaming",
                },
                {
                    "id": "launch-2",
                    "title": "써멀라이트 TL-UB 국내 출시",
                    "url": "https://example.com/product-news",
                    "source_name": "NewsTap Product News",
                    "shorts_score": 95,
                    "event_type": "product_launch",
                    "topic_bucket": "peripheral_wearable_audio",
                },
                {
                    "id": "general-1",
                    "title": "GPU supply chain expands for AI servers",
                    "url": "https://example.com/gpu-supply",
                    "source_name": "theverge",
                    "shorts_score": 80,
                    "event_type": "market_context",
                    "topic_bucket": "ai_infra",
                },
            ]
            for row in rows:
                con.execute(
                    "INSERT INTO articles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        row["id"],
                        json.dumps(row),
                        row["title"],
                        row["url"],
                        row["url"],
                        row["source_name"],
                        row["shorts_score"],
                        row["event_type"],
                        row["topic_bucket"],
                        "2026-06-09T00:00:00Z",
                        "2026-06-09T00:00:00Z",
                        "2026-06-09T00:00:00Z",
                        "not_generated",
                    ),
                )
            con.commit()
            con.close()

            with patch.object(job, "ARCHIVE_DB", db_path), patch.object(
                job, "collect_ranked_news", return_value=[]
            ), patch.object(job, "load_upload_history", return_value=[]):
                selected = job.select_next_article(limit=10, topic="")

        self.assertEqual(selected["url"], "https://example.com/gpu-supply")


if __name__ == "__main__":
    unittest.main()
