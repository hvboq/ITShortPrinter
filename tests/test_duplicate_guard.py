import sys
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from news.duplicate_guard import (  # noqa: E402
    active_history_items,
    canonicalize_url,
    duplicate_reason,
    is_stale_pending_upload,
    load_history,
    titles_similar,
    write_history,
)


class DuplicateGuardTests(unittest.TestCase):
    def test_canonicalize_url_ignores_tracking_and_www(self):
        self.assertEqual(
            canonicalize_url("https://www.example.com/news/allwinner/?utm_source=x&ref=feed&id=7#top"),
            "https://example.com/news/allwinner?id=7",
        )

    def test_duplicate_reason_matches_nested_canonical_article_url(self):
        history = [
            {
                "article_title": "Allwinner unveils new RISC-V chip",
                "article_url": "https://news.example.com/allwinner-chip?utm_source=feed",
            }
        ]
        candidate = {
            "title": "Different generated title",
            "article": {"canonical_url": "https://news.example.com/allwinner-chip"},
        }

        self.assertEqual(duplicate_reason(candidate, history), "url")

    def test_duplicate_reason_matches_highly_similar_titles(self):
        history = [{"article_title": "Allwinner announces new AI chip for low cost devices"}]
        candidate = {"article_title": "Allwinner announces new AI chip for low-cost devices"}

        self.assertTrue(titles_similar(candidate["article_title"], history[0]["article_title"]))
        self.assertEqual(duplicate_reason(candidate, history), "title_similarity")

    def test_stale_pending_upload_reservation_does_not_block_candidate(self):
        now = time.time()
        stale_pending = {
            "article_title": "Nvidia launches a new GPU",
            "article_url": "https://example.com/gpu",
            "upload_status": "pending_upload",
            "reserved_at_unix": now - 25 * 60 * 60,
        }
        recent_pending = {
            "article_title": "AMD launches a new GPU",
            "article_url": "https://example.com/amd-gpu",
            "upload_status": "pending_upload",
            "reserved_at_unix": now,
        }

        self.assertTrue(is_stale_pending_upload(stale_pending, now=now))
        self.assertFalse(is_stale_pending_upload(recent_pending, now=now))
        self.assertEqual(active_history_items([stale_pending, recent_pending], now=now), [recent_pending])
        self.assertIsNone(duplicate_reason({"article_url": "https://example.com/gpu"}, [stale_pending]))
        self.assertEqual(duplicate_reason({"article_url": "https://example.com/amd-gpu"}, [recent_pending]), "url")

    def test_load_history_fails_closed_on_corrupt_json(self):
        path = Path(self.id().replace(".", "_"))
        path.write_text("{not-json", encoding="utf-8")
        try:
            with self.assertRaises(ValueError):
                load_history(path)
        finally:
            path.unlink(missing_ok=True)

    def test_write_history_uses_requested_json_shape(self):
        path = Path(self.id().replace(".", "_"))
        try:
            write_history(path, [{"article_url": "https://example.com/story"}])
            self.assertEqual(load_history(path), [{"article_url": "https://example.com/story"}])
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
