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
    titles_similar,
)


class DuplicateGuardTests(unittest.TestCase):
    def test_semantic_topic_duplicates_only_block_within_72_hours(self):
        now = 2_000_000_000.0
        candidate = {
            "article_title": "Samsung starts HBM4 mass production for Nvidia supply",
            "article_url": "https://new.example.com/hbm4-production",
        }
        recent = {
            "article_title": "Nvidia supply secured as Samsung begins mass production of HBM4",
            "article_url": "https://old.example.com/samsung-hbm4",
            "uploaded_at_unix": now - 71 * 60 * 60,
        }
        expired = dict(recent, uploaded_at_unix=now - 73 * 60 * 60)

        self.assertEqual(duplicate_reason(candidate, [recent], now=now), "semantic_topic")
        self.assertIsNone(duplicate_reason(candidate, [expired], now=now))

    def test_exact_url_is_permanently_blocked_but_stale_pending_is_ignored(self):
        now = 2_000_000_000.0
        candidate = {"article_url": "https://example.com/permanent?id=1&utm_source=new"}
        old_upload = {
            "article_url": "https://www.example.com/permanent?utm_medium=rss&id=1",
            "uploaded_at_unix": now - 365 * 24 * 60 * 60,
        }
        stale_pending = dict(
            old_upload,
            upload_status="pending_upload",
            reserved_at_unix=now - 7 * 60 * 60,
        )

        self.assertEqual(duplicate_reason(candidate, [old_upload], now=now), "url")
        self.assertIsNone(duplicate_reason(candidate, [stale_pending], now=now))

    def test_semantic_topic_dedupe_does_not_merge_distinct_product_generations(self):
        now = 2_000_000_000.0
        history = [{
            "article_title": "Samsung Galaxy S26 Ultra starts shipping in Korea",
            "uploaded_at_unix": now - 60,
        }]
        candidate = {"article_title": "Samsung begins Korea shipments of Galaxy S27 Ultra"}

        self.assertIsNone(duplicate_reason(candidate, history, now=now))
        self.assertIsNone(duplicate_reason(
            {"article_title": "Galaxy S27 Ultra officially launched"},
            [{"article_title": "Galaxy S26 Ultra officially launched", "uploaded_at_unix": now - 60}],
            now=now,
        ))

    def test_korean_english_synonyms_and_compact_models_are_semantic_duplicates(self):
        now = 2_000_000_000.0
        examples = [
            ("애플 아이폰18 사전예약 시작", "Apple begins pre-orders for iPhone 18"),
            ("SK하이닉스 HBM4 양산 시작", "SK Hynix begins mass production of HBM4"),
            ("AMD 라이젠 9 9900X3D 예약 판매", "AMD Ryzen 9 9900X3D pre-order sales begin"),
        ]
        for candidate_title, old_title in examples:
            with self.subTest(candidate_title=candidate_title):
                self.assertEqual(duplicate_reason(
                    {"article_title": candidate_title},
                    [{"article_title": old_title, "uploaded_at_unix": now - 60}],
                    now=now,
                ), "semantic_topic")

    def test_semantic_dedupe_keeps_different_supplier_or_event_distinct(self):
        now = 2_000_000_000.0
        self.assertIsNone(duplicate_reason(
            {"article_title": "삼성 HBM4 대량 생산 시작"},
            [{"article_title": "SK Hynix starts HBM4 mass production", "uploaded_at_unix": now - 60}],
            now=now,
        ))
        self.assertIsNone(duplicate_reason(
            {"article_title": "Samsung starts HBM4 mass production for Nvidia"},
            [{"article_title": "SK Hynix begins Nvidia HBM4 mass production", "uploaded_at_unix": now - 60}],
            now=now,
        ))
        self.assertIsNone(duplicate_reason(
            {"article_title": "Apple iPhone 18 pre-orders begin"},
            [{"article_title": "Apple launches iPhone 18 review", "uploaded_at_unix": now - 60}],
            now=now,
        ))

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


if __name__ == "__main__":
    unittest.main()
