import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SRC_DIR = PROJECT_ROOT / "src"
for path in (str(SCRIPTS_DIR), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

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


if __name__ == "__main__":
    unittest.main()
