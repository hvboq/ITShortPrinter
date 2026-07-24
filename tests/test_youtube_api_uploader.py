import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class YouTubeApiUploaderTests(unittest.TestCase):
    def test_default_oauth_scopes_cover_setup_and_channel_checked_uploads(self):
        from youtube_api.auth import (
            ANALYTICS_SCOPES,
            CHANNEL_UPLOAD_SCOPES,
            DEFAULT_SCOPES,
            MANAGE_SCOPES,
            UPLOAD_SCOPES,
            YOUTUBE_READONLY_SCOPES,
        )

        self.assertEqual(
            set(DEFAULT_SCOPES),
            set(YOUTUBE_READONLY_SCOPES + ANALYTICS_SCOPES + UPLOAD_SCOPES),
        )
        self.assertEqual(
            set(CHANNEL_UPLOAD_SCOPES),
            set(YOUTUBE_READONLY_SCOPES + UPLOAD_SCOPES),
        )
        self.assertTrue(set(MANAGE_SCOPES).isdisjoint(DEFAULT_SCOPES))

    def test_build_video_body_uses_upload_metadata_and_visibility(self):
        from youtube_api.uploader import build_video_body

        body = build_video_body(
            title="  한국어   쇼츠 제목  ",
            description="desc",
            visibility="public",
            made_for_kids=False,
        )

        self.assertEqual(body["snippet"]["title"], "한국어 쇼츠 제목")
        self.assertEqual(body["snippet"]["description"], "desc")
        self.assertEqual(body["snippet"]["categoryId"], "28")
        self.assertEqual(body["status"]["privacyStatus"], "public")
        self.assertFalse(body["status"]["selfDeclaredMadeForKids"])

    def test_build_video_body_rejects_uuid_title_and_unknown_visibility(self):
        from youtube_api.uploader import build_video_body

        with self.assertRaises(ValueError):
            build_video_body("726602c6 9c2a 4a39 b94a 0715d2bcc695")

        with self.assertRaises(ValueError):
            build_video_body("정상 제목", visibility="friends")

    def test_upload_video_calls_youtube_videos_insert(self):
        from youtube_api import uploader

        class FakeMediaFileUpload:
            def __init__(self, filename, mimetype, resumable):
                self.filename = filename
                self.mimetype = mimetype
                self.resumable = resumable

        class FakeRequest:
            def execute(self):
                return {"id": "abc123"}

        class FakeVideos:
            def __init__(self):
                self.insert_kwargs = None

            def insert(self, **kwargs):
                self.insert_kwargs = kwargs
                return FakeRequest()

        class FakeYouTube:
            def __init__(self):
                self.fake_videos = FakeVideos()

            def videos(self):
                return self.fake_videos

        fake_googleapiclient = types.ModuleType("googleapiclient")
        fake_http = types.ModuleType("googleapiclient.http")
        fake_http.MediaFileUpload = FakeMediaFileUpload

        with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
            youtube = FakeYouTube()
            with patch.dict(
                sys.modules,
                {
                    "googleapiclient": fake_googleapiclient,
                    "googleapiclient.http": fake_http,
                },
            ):
                result = uploader.upload_video(
                    tmp.name,
                    title="API 업로드 테스트",
                    description="설명",
                    visibility="unlisted",
                    youtube_service=youtube,
                )

        kwargs = youtube.fake_videos.insert_kwargs
        self.assertEqual(result["video_id"], "abc123")
        self.assertEqual(result["uploaded_url"], "https://youtu.be/abc123")
        self.assertEqual(kwargs["part"], "snippet,status")
        self.assertEqual(kwargs["body"]["snippet"]["title"], "API 업로드 테스트")
        self.assertEqual(kwargs["body"]["status"]["privacyStatus"], "unlisted")
        self.assertFalse(kwargs["notifySubscribers"])
        self.assertEqual(kwargs["media_body"].mimetype, "video/*")
        self.assertTrue(kwargs["media_body"].resumable)

    def test_upload_video_rejects_unexpected_authorized_channel(self):
        from youtube_api import uploader

        class FakeMediaFileUpload:
            def __init__(self, filename, mimetype, resumable):
                self.filename = filename
                self.mimetype = mimetype
                self.resumable = resumable

        class FakeRequest:
            def __init__(self, response):
                self.response = response

            def execute(self):
                return self.response

        class FakeChannels:
            def list(self, **_kwargs):
                return FakeRequest({"items": [{"id": "actual-channel"}]})

        class FakeVideos:
            def insert(self, **_kwargs):
                raise AssertionError("upload should not start for the wrong channel")

        class FakeYouTube:
            def channels(self):
                return FakeChannels()

            def videos(self):
                return FakeVideos()

        fake_googleapiclient = types.ModuleType("googleapiclient")
        fake_http = types.ModuleType("googleapiclient.http")
        fake_http.MediaFileUpload = FakeMediaFileUpload

        with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
            with patch.dict(
                sys.modules,
                {
                    "googleapiclient": fake_googleapiclient,
                    "googleapiclient.http": fake_http,
                },
            ):
                with self.assertRaises(RuntimeError):
                    uploader.upload_video(
                        tmp.name,
                        title="API 업로드 테스트",
                        youtube_service=FakeYouTube(),
                        expected_channel_id="expected-channel",
                    )

    def test_upload_video_requires_expected_channel_for_public_visibility(self):
        from youtube_api import uploader

        with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
            with self.assertRaises(ValueError):
                uploader.upload_video(
                    tmp.name,
                    title="Public upload",
                    visibility="public",
                    youtube_service=object(),
                )


if __name__ == "__main__":
    unittest.main()
