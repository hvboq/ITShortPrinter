import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class EdgeTtsProviderTests(unittest.TestCase):
    def test_edge_tts_provider_uses_korean_voice_and_converts_to_wav(self):
        import classes.Tts as tts_module
        from classes.Tts import TTS

        calls = {}

        class FakeCommunicate:
            def __init__(self, text, voice):
                calls["text"] = text
                calls["voice"] = voice

            async def save(self, path):
                calls["mp3_path"] = path
                Path(path).write_bytes(b"fake mp3 bytes")

        def fake_run(coro):
            return asyncio.run(coro)

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "voice.wav"
            with patch.object(tts_module, "get_tts_provider", return_value="edge"), patch.object(
                tts_module, "get_tts_voice", return_value="ko-KR-SunHiNeural"
            ), patch.dict(
                sys.modules, {"edge_tts": type("FakeEdgeModule", (), {"Communicate": FakeCommunicate})}
            ), patch.object(
                tts_module, "_run_async", side_effect=fake_run
            ), patch.object(
                tts_module, "_convert_audio_to_wav", side_effect=lambda src, dst: Path(dst).write_bytes(b"RIFFfakewav")
            ) as convert:
                tts = TTS()
                result = tts.synthesize("한국어 뉴스 대본입니다.", str(output))

            self.assertEqual(result, str(output))
            self.assertEqual(calls["text"], "한국어 뉴스 대본입니다.")
            self.assertEqual(calls["voice"], "ko-KR-SunHiNeural")
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 0)
            convert.assert_called_once()


if __name__ == "__main__":
    unittest.main()
