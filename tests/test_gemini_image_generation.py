import base64
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class GeminiImageGenerationTests(unittest.TestCase):
    def test_build_payload_requests_image_with_vertical_aspect_ratio(self):
        from gemini_image import build_gemini_image_payload

        payload = build_gemini_image_payload("futuristic smartphone launch", "9:16")

        self.assertEqual(payload["contents"][0]["parts"][0]["text"], "futuristic smartphone launch")
        self.assertEqual(payload["generationConfig"]["responseModalities"], ["IMAGE"])
        self.assertEqual(payload["generationConfig"]["imageConfig"]["aspectRatio"], "9:16")

    def test_extract_image_bytes_accepts_inline_data_shapes(self):
        from gemini_image import extract_gemini_image_bytes

        png_bytes = b"\x89PNG\r\n\x1a\nfake-png"
        body = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": "image/png",
                                    "data": base64.b64encode(png_bytes).decode("ascii"),
                                }
                            }
                        ]
                    }
                }
            ]
        }

        self.assertEqual(extract_gemini_image_bytes(body), png_bytes)

    def test_generate_gemini_image_bytes_posts_to_generate_content_endpoint(self):
        from gemini_image import generate_gemini_image_bytes

        response = Mock()
        response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "inline_data": {
                                    "mime_type": "image/png",
                                    "data": base64.b64encode(b"image-bytes").decode("ascii"),
                                }
                            }
                        ]
                    }
                }
            ]
        }
        response.raise_for_status.return_value = None

        import gemini_image

        fake_requests = Mock()
        fake_requests.post.return_value = response
        with patch.object(gemini_image, "requests", fake_requests):
            image_bytes = generate_gemini_image_bytes(
                prompt="vertical IT news visual",
                api_key="test-key",
                base_url="https://example.test/v1beta",
                model="gemini-test-image",
                aspect_ratio="9:16",
                timeout=10,
            )

        self.assertEqual(image_bytes, b"image-bytes")
        args, kwargs = fake_requests.post.call_args
        self.assertEqual(args[0], "https://example.test/v1beta/models/gemini-test-image:generateContent")
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "test-key")
        self.assertEqual(kwargs["json"]["generationConfig"]["imageConfig"]["aspectRatio"], "9:16")
        self.assertEqual(kwargs["timeout"], 10)


if __name__ == "__main__":
    unittest.main()
