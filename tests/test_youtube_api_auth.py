import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class YouTubeOAuthScopeTests(unittest.TestCase):
    def test_default_scopes_include_comment_analysis_scope_once(self):
        from youtube_api.auth import COMMENT_SCOPES, DEFAULT_SCOPES

        force_ssl = "https://www.googleapis.com/auth/youtube.force-ssl"
        self.assertEqual(COMMENT_SCOPES, [force_ssl])
        self.assertEqual(DEFAULT_SCOPES.count(force_ssl), 1)

    def test_default_scopes_are_stable_unique_superset(self):
        from youtube_api.auth import (
            COMMENT_SCOPES,
            DEFAULT_SCOPES,
            MANAGE_SCOPES,
            READONLY_SCOPES,
            UPLOAD_SCOPES,
        )

        expected = READONLY_SCOPES + UPLOAD_SCOPES + COMMENT_SCOPES + MANAGE_SCOPES
        self.assertEqual(DEFAULT_SCOPES, expected)
        self.assertEqual(len(DEFAULT_SCOPES), len(set(DEFAULT_SCOPES)))


if __name__ == "__main__":
    unittest.main()
