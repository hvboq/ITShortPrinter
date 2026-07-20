from __future__ import annotations

import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class ShortScriptPolicyTests(unittest.TestCase):
    def test_news_prompt_targets_30_to_40_seconds_and_question_preview_hook(self):
        from news.shorts import build_shorts_script_prompt

        prompt = build_shorts_script_prompt({"title": "새 칩 공개", "raw_excerpt": "성능 향상"})

        self.assertIn("30~40초", prompt)
        self.assertIn("질문형", prompt)
        self.assertIn("첫 3초", prompt)
        self.assertIn("답의 방향", prompt)
        self.assertNotIn("45~60초", prompt)

    def test_generic_prompt_and_review_apply_same_opening_policy(self):
        from classes.YouTube import YouTube

        youtube = YouTube.for_local_generation()
        youtube.subject = "새 노트북 칩"
        calls = []

        def fake_generate(prompt, model_name=None):
            calls.append(prompt)
            if "JSON만 반환" in prompt:
                return '{"approved": true, "score": 95, "issues": [], "revised_script": "이 칩이 배터리를 바꿀까요? 결론부터 말하면 사용 시간이 핵심입니다."}'
            return "이 칩이 배터리를 바꿀까요? 결론부터 말하면 사용 시간이 핵심입니다."

        with patch.object(youtube, "generate_response", side_effect=fake_generate), patch(
            "classes.YouTube.get_script_review_enabled", return_value=True
        ), patch.object(youtube, "_persist_script_review"):
            youtube.generate_script()

        self.assertIn("30~40초", calls[0])
        self.assertIn("질문형", calls[0])
        self.assertIn("답의 방향", calls[0])
        self.assertIn("30~40초", calls[1])
        self.assertIn("질문형", calls[1])
        self.assertIn("답의 방향", calls[1])


class FeedbackSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 20, 12, tzinfo=timezone.utc)

    def video(self, video_id, age_hours, topic="chip", views=1000):
        return {
            "video_id": video_id,
            "published_at": (self.now - timedelta(hours=age_hours)).isoformat(),
            "title": video_id,
            "topic_bucket": topic,
            "views": views,
            "likes": 50,
            "comments": 5,
        }

    def test_excludes_under_48h_and_captures_eligible_video_once(self):
        from youtube_api.feedback import merge_48h_snapshots

        videos = [self.video("young", 47.99), self.video("ready", 48)]
        analytics = {"ready": {"average_view_percentage": 85, "average_view_duration_seconds": 31}}
        first = merge_48h_snapshots([], videos, analytics, now=self.now)
        second = merge_48h_snapshots(first, [self.video("ready", 72, views=9999)], analytics, now=self.now)

        self.assertEqual([row["video_id"] for row in first], ["ready"])
        self.assertEqual(first, second)
        self.assertEqual(first[0]["status"], "captured")
        self.assertEqual(first[0]["views"], 1000)

    def test_new_snapshots_are_limited_to_48_through_72_hours(self):
        from youtube_api.feedback import merge_48h_snapshots

        videos = [
            self.video("47_9", 47.9),
            self.video("48", 48),
            self.video("60", 60),
            self.video("over72", 72.01),
        ]
        analytics = {
            video_id: {"average_view_percentage": 80}
            for video_id in ("48", "60", "over72")
        }

        rows = merge_48h_snapshots([], videos, analytics, now=self.now)

        self.assertEqual([row["video_id"] for row in rows], ["48", "60"])
        self.assertEqual([row["actual_age_hours"] for row in rows], [48.0, 60.0])
        self.assertTrue(all(row["trainable"] for row in rows))

    def test_analytics_pending_record_can_be_refreshed_later(self):
        from youtube_api.feedback import merge_48h_snapshots

        pending = merge_48h_snapshots([], [self.video("late", 49)], {}, now=self.now)
        refreshed = merge_48h_snapshots(
            pending,
            [self.video("late", 60, views=1400)],
            {"late": {"average_view_percentage": 78, "average_view_duration_seconds": 29}},
            now=self.now + timedelta(hours=12),
        )

        self.assertEqual(len(refreshed), 1)
        self.assertEqual(pending[0]["status"], "analytics_pending")
        self.assertEqual(refreshed[0]["status"], "captured")
        self.assertEqual(refreshed[0]["views"], 1400)
        self.assertEqual(refreshed[0]["average_view_percentage"], 78.0)

    def test_pending_retry_survives_window_but_late_capture_is_not_trainable(self):
        from youtube_api.feedback import merge_48h_snapshots

        pending = merge_48h_snapshots([], [self.video("retry", 60)], {}, now=self.now)
        retry_now = self.now + timedelta(hours=13)
        refreshed = merge_48h_snapshots(
            pending,
            [self.video("retry", 60, views=1500)],
            {"retry": {"average_view_percentage": 75}},
            now=retry_now,
        )

        self.assertEqual(len(refreshed), 1)
        self.assertEqual(refreshed[0]["status"], "captured")
        self.assertEqual(refreshed[0]["actual_age_hours"], 73.0)
        self.assertFalse(refreshed[0]["trainable"])

    def test_analytics_window_is_fixed_at_published_plus_48_hours(self):
        from youtube_api.feedback import analytics_date_window

        self.assertEqual(
            analytics_date_window("2026-07-18T12:30:00+00:00"),
            ("2026-07-18", "2026-07-20"),
        )

    def test_weekly_weights_require_samples_shrink_and_clamp(self):
        from youtube_api.feedback import build_weekly_feedback

        snapshots = []
        for i in range(10):
            snapshots.append({"video_id": f"good{i}", "topic_bucket": "good", "status": "captured", "trainable": True, "actual_age_hours": 48, "views": 10000, "average_view_percentage": 100, "likes": 500})
            snapshots.append({"video_id": f"bad{i}", "topic_bucket": "bad", "status": "captured", "trainable": True, "actual_age_hours": 48, "views": 10, "average_view_percentage": 10, "likes": 0})
        snapshots.append({"video_id": "tiny", "topic_bucket": "tiny", "status": "captured", "trainable": True, "actual_age_hours": 48, "views": 999999, "average_view_percentage": 200, "likes": 999})
        snapshots.extend([
            {"video_id": "legacy", "topic_bucket": "legacy", "status": "captured", "views": 999999},
            {"video_id": "late", "topic_bucket": "late", "status": "captured", "trainable": True, "actual_age_hours": 80, "views": 999999},
        ])

        result = build_weekly_feedback(snapshots, minimum_sample=3, shrinkage=5, min_weight=0.8, max_weight=1.2)

        self.assertEqual(result["runtime_weights"]["tiny"], 1.0)
        self.assertLessEqual(result["runtime_weights"]["good"], 1.2)
        self.assertGreaterEqual(result["runtime_weights"]["bad"], 0.8)
        self.assertGreater(result["runtime_weights"]["good"], result["runtime_weights"]["bad"])
        self.assertEqual(result["policy"]["minimum_sample"], 3)
        self.assertNotIn("legacy", result["runtime_weights"])
        self.assertNotIn("late", result["runtime_weights"])

    def test_feedback_config_is_safely_bounded(self):
        import config

        with patch.object(config, "load_config", return_value={"youtube_feedback": {
            "minimum_sample": 0, "shrinkage": -4, "min_weight": -2, "max_weight": 99
        }}):
            value = config.get_youtube_feedback_config()

        self.assertGreaterEqual(value["minimum_sample"], 2)
        self.assertGreater(value["shrinkage"], 0)
        self.assertGreaterEqual(value["min_weight"], 0.5)
        self.assertLessEqual(value["max_weight"], 1.5)

    def test_channel_identity_mismatch_is_rejected(self):
        from youtube_api.feedback import require_expected_channel

        with self.assertRaisesRegex(RuntimeError, "channel"):
            require_expected_channel("wrong", "expected")

    def test_title_is_classified_and_existing_general_bucket_is_migrated(self):
        from youtube_api.feedback import infer_topic_bucket_from_title, merge_48h_snapshots

        self.assertEqual(
            infer_topic_bucket_from_title("SK하이닉스 HBM4 양산, 엔비디아 GPU 공급 확대"),
            "pc_chip_device",
        )
        existing = [{
            "video_id": "ready",
            "status": "captured",
            "topic_bucket": "general_it",
            "views": 100,
            "published_at": (self.now - timedelta(hours=60)).isoformat(),
        }]
        video = self.video("ready", 60, topic="pc_chip_device", views=999)
        migrated = merge_48h_snapshots(existing, [video], {}, now=self.now)
        self.assertEqual(migrated[0]["topic_bucket"], "pc_chip_device")
        self.assertEqual(migrated[0]["views"], 100)

    def test_transient_analytics_error_becomes_pending_but_auth_error_is_fatal(self):
        from youtube_api.feedback import query_analytics_or_pending

        class Response:
            def __init__(self, status):
                self.status = status

        class ApiError(Exception):
            def __init__(self, status):
                self.resp = Response(status)

        self.assertEqual(query_analytics_or_pending(lambda: (_ for _ in ()).throw(ApiError(500))), {})
        with self.assertRaises(ApiError):
            query_analytics_or_pending(lambda: (_ for _ in ()).throw(ApiError(403)))


class FeedbackCliTests(unittest.TestCase):
    def test_new_scripts_support_help_without_oauth(self):
        for script in ("collect_youtube_48h_performance.py", "build_weekly_youtube_feedback.py"):
            result = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "scripts" / script), "--help"],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("usage:", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
