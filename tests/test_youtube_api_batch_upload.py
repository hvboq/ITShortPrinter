import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SRC_DIR = PROJECT_ROOT / "src"
for path in (str(SCRIPTS_DIR), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import youtube_api_batch_upload  # noqa: E402
from youtube_api_batch_upload import build_upload_description  # noqa: E402


class YouTubeApiBatchUploadTests(unittest.TestCase):
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
                    visibility="public",
                    update_history=True,
                    update_archive=False,
                    start_label="START",
                    done_label="DONE",
                )

            self.assertEqual(results, [])
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
                    visibility="public",
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


if __name__ == "__main__":
    unittest.main()
