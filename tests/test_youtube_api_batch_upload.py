import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SRC_DIR = PROJECT_ROOT / "src"
for path in (str(SCRIPTS_DIR), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import youtube_api_batch_upload  # noqa: E402
from youtube_api_batch_upload import build_upload_description  # noqa: E402


class YouTubeApiBatchUploadTests(unittest.TestCase):
    def test_quality_gate_requires_exact_overall_pass(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(
                youtube_api_batch_upload._quality_failed(
                    {"review_quality_pass": True}
                )
            )
            self.assertEqual(
                youtube_api_batch_upload._quality_failure_reason(
                    {"review_quality_pass": True}
                ),
                "quality_fields_incomplete",
            )
            self.assertTrue(
                youtube_api_batch_upload._quality_failed(
                    {"overall_quality_pass": "true"}
                )
            )
            self.assertFalse(
                youtube_api_batch_upload._quality_failed(
                    {"overall_quality_pass": True}
                )
            )

    def test_build_upload_description_appends_source_article_url(self):
        description = build_upload_description(
            "오늘의 IT 뉴스 요약입니다.",
            "https://example.com/original-article",
        )

        self.assertEqual(
            description,
            "오늘의 IT 뉴스 요약입니다.\n\n원본 기사: https://example.com/original-article",
        )

    def test_build_upload_description_does_not_duplicate_existing_source_url(self):
        description = build_upload_description(
            "요약입니다.\n\n원본 기사: https://example.com/original-article",
            "https://example.com/original-article",
        )

        self.assertEqual(description.count("원본 기사:"), 1)

    def test_build_upload_description_preserves_source_url_when_base_is_long(self):
        url = "https://example.com/original-article"
        description = build_upload_description("가" * 5000, url)

        self.assertLessEqual(len(description), 4500)
        self.assertTrue(description.endswith(f"원본 기사: {url}"))

    def test_upload_manifest_skips_duplicate_before_api_call(self):
        import json
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            video = tmp / "video.mp4"
            video.write_bytes(b"placeholder")
            manifest = tmp / "manifest.json"
            output = tmp / "uploaded.json"
            history = tmp / "upload_history.json"
            lock = tmp / "upload_history.lock"
            history.write_text(
                json.dumps(
                    [
                        {
                            "article_title": "Allwinner announces new AI chip for low cost devices",
                            "article_url": "https://news.example.com/allwinner-chip",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            manifest.write_text(
                json.dumps(
                    [
                        {
                            "rank": 1,
                            "video_path": str(video),
                            "article_title": "Allwinner announces new AI chip for low-cost devices",
                            "article_url": "https://news.example.com/allwinner-chip?utm_source=feed",
                            "metadata": {"title": "Allwinner AI chip update"},
                            "overall_quality_pass": True,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(youtube_api_batch_upload, "UPLOAD_HISTORY", history), patch.object(
                youtube_api_batch_upload, "UPLOAD_HISTORY_LOCK", lock
            ), patch.object(youtube_api_batch_upload, "get_youtube_channel_config", return_value={"id": ""}), patch.object(
                youtube_api_batch_upload, "upload_video"
            ) as upload_mock:
                results = youtube_api_batch_upload.upload_manifest_with_api(
                    source_manifest=manifest,
                    output_manifest=output,
                    visibility="unlisted",
                    update_history=True,
                    update_archive=False,
                    start_label="START",
                    done_label="DONE",
                )

            self.assertEqual(len(results), 1)
            self.assertTrue(results[0]["skipped"])
            self.assertEqual(results[0]["skip_reason"], "duplicate_url")
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(written, results)
            upload_mock.assert_not_called()

    def test_upload_manifest_reserves_article_and_finalizes_history(self):
        import json
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            video = tmp / "video.mp4"
            video.write_bytes(b"placeholder")
            manifest = tmp / "manifest.json"
            output = tmp / "uploaded.json"
            history = tmp / "upload_history.json"
            lock = tmp / "upload_history.lock"
            manifest.write_text(
                json.dumps(
                    [
                        {
                            "rank": 1,
                            "video_path": str(video),
                            "article_title": "Unique GPU supply news",
                            "article_url": "https://news.example.com/unique-gpu",
                            "metadata": {"title": "Unique GPU supply news"},
                            "overall_quality_pass": True,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(youtube_api_batch_upload, "UPLOAD_HISTORY", history), patch.object(
                youtube_api_batch_upload, "UPLOAD_HISTORY_LOCK", lock
            ), patch.object(youtube_api_batch_upload, "get_youtube_channel_config", return_value={"id": ""}), patch.object(
                youtube_api_batch_upload,
                "upload_video",
                return_value={
                    "title": "Unique GPU supply news",
                    "description": "",
                    "visibility": "public",
                    "video_id": "abc123",
                    "uploaded_url": "https://youtu.be/abc123",
                },
            ) as upload_mock:
                results = youtube_api_batch_upload.upload_manifest_with_api(
                    source_manifest=manifest,
                    output_manifest=output,
                    visibility="unlisted",
                    update_history=True,
                    update_archive=False,
                    start_label="START",
                    done_label="DONE",
                )

            saved_history = json.loads(history.read_text(encoding="utf-8"))
            self.assertEqual(len(results), 1)
            upload_mock.assert_called_once()
            self.assertEqual(saved_history[0]["video_id"], "abc123")
            self.assertNotEqual(saved_history[0].get("upload_status"), "pending_upload")

    def test_upload_manifest_skips_failed_review_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            video_path = tmp_path / "bad-short.mp4"
            video_path.write_bytes(b"not a real upload in this unit test")
            source_manifest = tmp_path / "manifest.json"
            output_manifest = tmp_path / "upload-manifest.json"
            source_manifest.write_text(
                json.dumps(
                    [
                        {
                            "rank": 1,
                            "video_path": str(video_path),
                            "article_title": "Short that needs review",
                            "article_url": "https://example.com/review",
                            "article_id": "review-1",
                            "source": "Example",
                            "metadata": {"title": "검수 필요 쇼츠"},
                            "review_quality_pass": False,
                            "review_warnings": ["audio_silent", "video_duration_under_5s"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch.object(
                youtube_api_batch_upload,
                "get_youtube_channel_config",
                return_value={"slug": "test", "name": "", "id": ""},
            ), patch.object(youtube_api_batch_upload, "upload_video") as upload_video, patch.object(
                youtube_api_batch_upload, "mark_shorts_status"
            ) as mark_status:
                results = youtube_api_batch_upload.upload_manifest_with_api(
                    source_manifest=source_manifest,
                    output_manifest=output_manifest,
                    visibility="unlisted",
                    update_history=False,
                    update_archive=True,
                    start_label="UPLOAD_TEST_START",
                    done_label="UPLOAD_TEST_DONE",
                )

            upload_video.assert_not_called()
            mark_status.assert_called_once_with(
                results[0],
                "needs_review",
                rank=1,
                video_path=str(video_path.resolve()),
            )
            self.assertEqual(results[0]["skip_reason"], "review_quality_failed")
            self.assertEqual(results[0]["review_warnings"], ["audio_silent", "video_duration_under_5s"])
            self.assertEqual(results[0]["structure_warnings"], [])
            written = json.loads(output_manifest.read_text(encoding="utf-8"))
            self.assertTrue(written[0]["skipped"])

    def test_upload_manifest_skips_structure_quality_failures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            video_path = tmp_path / "structural-fail-short.mp4"
            video_path.write_bytes(b"not a real upload in this unit test")
            source_manifest = tmp_path / "manifest.json"
            output_manifest = tmp_path / "upload-manifest.json"
            source_manifest.write_text(
                json.dumps(
                    [
                        {
                            "rank": 1,
                            "video_path": str(video_path),
                            "article_title": "Short with weak structure",
                            "article_url": "https://example.com/structure",
                            "article_id": "structure-1",
                            "source": "Example",
                            "metadata": {"title": "구조 검수 필요 쇼츠"},
                            "review_quality_pass": True,
                            "structure_quality_pass": False,
                            "overall_quality_pass": False,
                            "review_warnings": [],
                            "structure_warnings": ["structure_script_too_short"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch.object(
                youtube_api_batch_upload,
                "get_youtube_channel_config",
                return_value={"slug": "test", "name": "", "id": ""},
            ), patch.object(youtube_api_batch_upload, "upload_video") as upload_video, patch.object(
                youtube_api_batch_upload, "mark_shorts_status"
            ) as mark_status:
                results = youtube_api_batch_upload.upload_manifest_with_api(
                    source_manifest=source_manifest,
                    output_manifest=output_manifest,
                    visibility="unlisted",
                    update_history=False,
                    update_archive=True,
                    start_label="UPLOAD_TEST_START",
                    done_label="UPLOAD_TEST_DONE",
                )

            upload_video.assert_not_called()
            mark_status.assert_called_once_with(
                results[0],
                "needs_review",
                rank=1,
                video_path=str(video_path.resolve()),
            )
            self.assertEqual(results[0]["skip_reason"], "structure_quality_failed")
            self.assertEqual(results[0]["structure_warnings"], ["structure_script_too_short"])

    def test_upload_manifest_skips_placeholder_visuals(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            video_path = tmp_path / "placeholder-short.mp4"
            video_path.write_bytes(b"not a real upload in this unit test")
            source_manifest = tmp_path / "manifest.json"
            output_manifest = tmp_path / "upload-manifest.json"
            source_manifest.write_text(
                json.dumps(
                    [
                        {
                            "rank": 1,
                            "video_path": str(video_path),
                            "article_title": "Short with placeholder art",
                            "article_url": "https://example.com/placeholder",
                            "metadata": {"title": "플레이스홀더 차단 쇼츠"},
                            "review_quality_pass": True,
                            "structure_quality_pass": False,
                            "overall_quality_pass": False,
                            "placeholder_visuals_used": True,
                            "placeholder_visual_reasons": ["Hermes image queue empty"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch.object(
                youtube_api_batch_upload,
                "get_youtube_channel_config",
                return_value={"slug": "test", "name": "", "id": ""},
            ), patch.object(youtube_api_batch_upload, "upload_video") as upload_video:
                results = youtube_api_batch_upload.upload_manifest_with_api(
                    source_manifest=source_manifest,
                    output_manifest=output_manifest,
                    visibility="unlisted",
                    update_history=False,
                    update_archive=False,
                    start_label="UPLOAD_TEST_START",
                    done_label="UPLOAD_TEST_DONE",
                )

            upload_video.assert_not_called()
            self.assertEqual(results[0]["skip_reason"], "placeholder_visuals_used")
            self.assertTrue(results[0]["placeholder_visuals_used"])
            self.assertEqual(results[0]["placeholder_visual_reasons"], ["Hermes image queue empty"])

    def test_upload_manifest_skips_missing_quality_fields_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            video_path = tmp_path / "legacy-short.mp4"
            video_path.write_bytes(b"not a real upload in this unit test")
            source_manifest = tmp_path / "manifest.json"
            output_manifest = tmp_path / "upload-manifest.json"
            source_manifest.write_text(
                json.dumps(
                    [
                        {
                            "rank": 1,
                            "video_path": str(video_path),
                            "article_title": "Legacy manifest without review fields",
                            "article_url": "https://example.com/legacy",
                            "metadata": {"title": "검수 필드 없는 쇼츠"},
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True), patch.object(
                youtube_api_batch_upload,
                "get_youtube_channel_config",
                return_value={"slug": "test", "name": "", "id": ""},
            ), patch.object(youtube_api_batch_upload, "upload_video") as upload_video:
                results = youtube_api_batch_upload.upload_manifest_with_api(
                    source_manifest=source_manifest,
                    output_manifest=output_manifest,
                    visibility="unlisted",
                    update_history=False,
                    update_archive=False,
                    start_label="UPLOAD_TEST_START",
                    done_label="UPLOAD_TEST_DONE",
                )

            upload_video.assert_not_called()
            self.assertEqual(results[0]["skip_reason"], "quality_fields_missing")

    def test_public_upload_requires_explicit_opt_in_and_channel_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_manifest = tmp_path / "manifest.json"
            output_manifest = tmp_path / "upload-manifest.json"

            with patch.dict(os.environ, {}, clear=True), patch.object(
                youtube_api_batch_upload,
                "get_youtube_channel_config",
                return_value={"slug": "test", "name": "", "id": ""},
            ):
                with self.assertRaises(RuntimeError):
                    youtube_api_batch_upload.upload_manifest_with_api(
                        source_manifest=source_manifest,
                        output_manifest=output_manifest,
                        visibility=" Public ",
                        update_history=True,
                        update_archive=True,
                        start_label="UPLOAD_TEST_START",
                        done_label="UPLOAD_TEST_DONE",
                    )


if __name__ == "__main__":
    unittest.main()
