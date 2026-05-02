import asyncio
import os
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

from config import ROOT_DIR, get_tts_provider, get_tts_voice

KITTEN_MODEL = "KittenML/kitten-tts-mini-0.8"
KITTEN_SAMPLE_RATE = 24000
EDGE_DEFAULT_VOICE = "ko-KR-SunHiNeural"


def _run_async(coro):
    """Run an async coroutine from sync code."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # This path is uncommon in the CLI, but keeps the helper safe if called from an existing loop.
    return loop.run_until_complete(coro)


def _convert_audio_to_wav(source_path: str, output_file: str) -> None:
    """Convert provider audio output to a PCM WAV file using imageio-ffmpeg's bundled ffmpeg."""
    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg = "ffmpeg"

    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            source_path,
            "-ac",
            "1",
            "-ar",
            str(KITTEN_SAMPLE_RATE),
            "-acodec",
            "pcm_s16le",
            output_file,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class TTS:
    def __init__(self) -> None:
        self._provider = get_tts_provider().strip().lower()
        self._voice = get_tts_voice()
        self._model = None

        if self._provider == "kitten":
            from kittentts import KittenTTS as KittenModel

            self._model = KittenModel(KITTEN_MODEL)
        elif self._provider not in {"silent", "edge"}:
            raise ValueError(
                f"Unsupported TTS provider '{self._provider}'. Expected 'kitten', 'edge', or 'silent'."
            )

    def synthesize(self, text, output_file=os.path.join(ROOT_DIR, ".mp", "audio.wav")):
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        if self._provider == "silent":
            return self._synthesize_silent(text, output_file)

        if self._provider == "edge":
            return self._synthesize_edge(text, output_file)

        import soundfile as sf

        audio = self._model.generate(text, voice=self._voice)
        sf.write(output_file, audio, KITTEN_SAMPLE_RATE)
        return output_file

    def _synthesize_silent(self, text, output_file):
        # Useful for smoke tests when KittenTTS and its heavy dependency chain are not installed.
        # Keep duration long enough for MoviePy/STT code paths to receive a valid non-empty WAV.
        duration_seconds = max(1.0, min(10.0, len(text) / 12.0))
        frame_count = int(KITTEN_SAMPLE_RATE * duration_seconds)
        silence_frame = struct.pack("<h", 0)

        with wave.open(output_file, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(KITTEN_SAMPLE_RATE)
            wav_file.writeframes(silence_frame * frame_count)

        return output_file

    def _synthesize_edge(self, text, output_file):
        """Generate Korean speech via Microsoft Edge TTS and convert it to WAV for MoviePy."""
        try:
            import edge_tts
        except ImportError as exc:
            raise ImportError(
                "edge-tts is required for tts_provider='edge'. Install it with: python -m pip install edge-tts"
            ) from exc

        voice = self._voice or EDGE_DEFAULT_VOICE
        if not voice.startswith("ko-"):
            voice = EDGE_DEFAULT_VOICE

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            mp3_path = tmp.name

        try:
            communicate = edge_tts.Communicate(text, voice)
            _run_async(communicate.save(mp3_path))
            _convert_audio_to_wav(mp3_path, output_file)
        finally:
            Path(mp3_path).unlink(missing_ok=True)

        return output_file
