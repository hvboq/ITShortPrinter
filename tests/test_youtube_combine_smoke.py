import os
import sys
import unittest
import wave
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class YouTubeCombineSmokeTests(unittest.TestCase):
    def _write_silent_wav(self, wav_path: Path, seconds: float = 1.0) -> None:
        sample_rate = 24000
        with wave.open(str(wav_path), "w") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(b"\x00\x00" * int(sample_rate * seconds))

    def _write_tone_wav(self, wav_path: Path, seconds: float = 1.0, amplitude: float = 0.7) -> None:
        sample_rate = 24000
        t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
        tone = amplitude * np.sin(2 * np.pi * 440 * t)
        samples = np.int16(tone * 32767)
        with wave.open(str(wav_path), "w") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(samples.tobytes())

    def test_combine_can_write_mp4_without_subtitle_dependencies(self):
        from PIL import Image
        from classes.YouTube import YouTube

        media_dir = PROJECT_ROOT / ".mp"
        songs_dir = PROJECT_ROOT / "Songs"
        media_dir.mkdir(exist_ok=True)
        songs_dir.mkdir(exist_ok=True)

        image_path = media_dir / "youtube-combine-smoke-image.png"
        tts_path = media_dir / "youtube-combine-smoke-tts.wav"
        song_path = songs_dir / "youtube-combine-smoke-song.wav"

        Image.new("RGB", (1080, 1920), color=(15, 22, 36)).save(image_path)
        for wav_path in [tts_path, song_path]:
            self._write_silent_wav(wav_path)

        youtube = object.__new__(YouTube)
        youtube.images = [str(image_path)]
        youtube.tts_path = str(tts_path)

        output_path = youtube.combine()

        self.assertTrue(Path(output_path).exists())
        self.assertGreater(os.path.getsize(output_path), 1000)

    def test_background_music_is_looped_to_match_narration_duration(self):
        from moviepy.editor import AudioFileClip
        from classes.youtube_composer import prepare_background_music

        media_dir = PROJECT_ROOT / ".mp"
        media_dir.mkdir(exist_ok=True)
        song_path = media_dir / "youtube-combine-short-song.wav"
        self._write_silent_wav(song_path, seconds=0.5)

        source = AudioFileClip(str(song_path))
        prepared = None
        try:
            prepared = prepare_background_music(source, duration=2.0, audio_fps=24000)
            self.assertAlmostEqual(prepared.duration, 2.0, places=2)
        finally:
            if prepared is not None:
                prepared.close()
            source.close()

    def test_background_music_fades_in_and_out_under_narration(self):
        from moviepy.editor import AudioFileClip
        from classes.youtube_composer import prepare_background_music

        media_dir = PROJECT_ROOT / ".mp"
        media_dir.mkdir(exist_ok=True)
        song_path = media_dir / "youtube-combine-tone-song.wav"
        self._write_tone_wav(song_path, seconds=2.0)

        source = AudioFileClip(str(song_path))
        prepared = None
        try:
            prepared = prepare_background_music(
                source,
                duration=2.0,
                audio_fps=24000,
                fade_seconds=0.5,
            )

            def peak_level(start: float, end: float) -> float:
                times = np.linspace(start, end, 24)
                frames = np.asarray(prepared.get_frame(times), dtype=float)
                return float(np.max(np.abs(frames)))

            start_level = peak_level(0.01, 0.05)
            middle_level = peak_level(0.75, 0.95)
            end_level = peak_level(1.95, 1.99)
            self.assertLess(start_level, middle_level)
            self.assertLess(end_level, middle_level)
        finally:
            if prepared is not None:
                prepared.close()
            source.close()

    def test_narration_audio_is_normalized_before_mixing(self):
        from moviepy.editor import AudioFileClip
        from classes.youtube_composer import prepare_narration_audio

        media_dir = PROJECT_ROOT / ".mp"
        media_dir.mkdir(exist_ok=True)
        narration_path = media_dir / "youtube-low-narration.wav"
        self._write_tone_wav(narration_path, seconds=1.0, amplitude=0.1)

        source = AudioFileClip(str(narration_path))
        prepared = None
        try:
            prepared = prepare_narration_audio(
                source,
                audio_fps=24000,
                target_peak=0.8,
                max_gain=10.0,
            )
            times = np.linspace(0.01, 0.99, 120)
            frames = np.asarray(prepared.get_frame(times), dtype=float)
            peak = float(np.max(np.abs(frames)))

            self.assertGreater(peak, 0.7)
            self.assertLess(peak, 0.85)
        finally:
            if prepared is not None:
                prepared.close()
            source.close()

    def test_audio_peak_level_falls_back_to_scalar_sampling(self):
        from moviepy.editor import AudioClip
        from classes.youtube_composer import _audio_peak_level
        from classes.youtube_composer import prepare_narration_audio

        def scalar_only_audio(_t):
            times = np.asarray(_t)
            if times.ndim > 0:
                raise IndexError("vector sampling unavailable")
            value = 0.1 * np.sin(2 * np.pi * 440 * float(times))
            return np.array([value, value], dtype=float)

        source = AudioClip(scalar_only_audio, duration=1.0, fps=24000)
        prepared = None
        try:
            self.assertGreater(_audio_peak_level(source), 0.09)
            prepared = prepare_narration_audio(
                source,
                audio_fps=24000,
                target_peak=0.8,
                max_gain=10.0,
            )
            self.assertGreater(_audio_peak_level(prepared), 0.7)
        finally:
            if prepared is not None and prepared is not source:
                prepared.close()
            source.close()

    def test_audio_peak_level_ignores_nonfinite_samples(self):
        from classes.youtube_composer import _audio_peak_level

        class MostlyFiniteAudio:
            duration = 1.0

            def get_frame(self, _t):
                times = np.asarray(_t)
                if times.ndim == 0:
                    return np.array([float("nan"), 0.42])
                return np.column_stack([
                    np.full(times.shape, float("nan")),
                    np.full(times.shape, 0.42),
                ])

        class NonfiniteAudio:
            duration = 1.0

            def get_frame(self, _t):
                times = np.asarray(_t)
                if times.ndim == 0:
                    return np.array([float("nan"), float("inf")])
                return np.column_stack([
                    np.full(times.shape, float("nan")),
                    np.full(times.shape, float("inf")),
                ])

        self.assertAlmostEqual(_audio_peak_level(MostlyFiniteAudio()), 0.42)
        self.assertEqual(_audio_peak_level(NonfiniteAudio()), 0.0)

    def test_final_audio_mix_is_limited_to_avoid_clipping(self):
        from moviepy.editor import AudioClip, CompositeAudioClip
        from classes.youtube_composer import _audio_peak_level
        from classes.youtube_composer import limit_audio_peak

        def constant_audio(_t):
            times = np.asarray(_t)
            if times.ndim == 0:
                return [0.72, 0.72]
            return np.column_stack([
                np.full(times.shape, 0.72),
                np.full(times.shape, 0.72),
            ])

        first = AudioClip(constant_audio, duration=1.0, fps=24000)
        second = AudioClip(constant_audio, duration=1.0, fps=24000)
        mixed = CompositeAudioClip([first, second])
        limited = None
        try:
            self.assertGreater(_audio_peak_level(mixed), 1.0)
            limited = limit_audio_peak(mixed, target_peak=0.9)
            self.assertLessEqual(_audio_peak_level(limited), 0.91)
        finally:
            if limited is not None and limited is not mixed:
                limited.close()
            mixed.close()
            first.close()
            second.close()

    def test_image_sequence_adds_motion_without_rapid_short_video_cuts(self):
        from PIL import Image
        from classes.youtube_composer import SHORTS_FRAME_SIZE
        from classes.youtube_composer import create_image_sequence

        media_dir = PROJECT_ROOT / ".mp"
        media_dir.mkdir(exist_ok=True)
        image_paths = []
        for index in range(5):
            image_path = media_dir / f"youtube-motion-source-{index}.png"
            Image.new("RGB", (1080, 1920), color=(15 + index * 20, 22, 36)).save(image_path)
            image_paths.append(str(image_path))

        clips = create_image_sequence(image_paths, duration=2.0, fps=12)
        try:
            self.assertLessEqual(len(clips), 2)
            self.assertTrue(all(tuple(clip.size) == SHORTS_FRAME_SIZE for clip in clips))
            self.assertTrue(all(clip.duration >= 1.0 for clip in clips))
        finally:
            for clip in clips:
                clip.close()

    def test_visual_timeline_reuses_images_to_avoid_long_static_holds(self):
        from classes.youtube_composer import MAX_VISUAL_CLIP_SECONDS
        from classes.youtube_composer import _select_visual_paths

        paths = ["visual-1.png", "visual-2.png", "visual-3.png"]
        timeline = _select_visual_paths(paths, duration=24.0)

        self.assertEqual(len(timeline), 4)
        self.assertLessEqual(24.0 / len(timeline), MAX_VISUAL_CLIP_SECONDS)
        self.assertEqual(timeline, ["visual-1.png", "visual-2.png", "visual-3.png", "visual-1.png"])

    def test_visual_timeline_still_limits_short_video_flash_cuts(self):
        from classes.youtube_composer import _select_visual_paths

        timeline = _select_visual_paths(
            ["visual-1.png", "visual-2.png", "visual-3.png", "visual-4.png", "visual-5.png"],
            duration=2.0,
        )

        self.assertEqual(timeline, ["visual-1.png", "visual-2.png"])

    def test_visual_motion_pans_within_scaled_frame_bounds(self):
        from classes.youtube_composer import SHORTS_FRAME_SIZE
        from classes.youtube_composer import _motion_position

        scale = 1.04
        extra_width = SHORTS_FRAME_SIZE[0] * scale - SHORTS_FRAME_SIZE[0]
        extra_height = SHORTS_FRAME_SIZE[1] * scale - SHORTS_FRAME_SIZE[1]

        start_x, start_y = _motion_position(0, progress=0.0, scale=scale)
        end_x, end_y = _motion_position(0, progress=1.0, scale=scale)

        self.assertNotEqual((start_x, start_y), (end_x, end_y))
        for x, y in [(start_x, start_y), (end_x, end_y)]:
            self.assertGreaterEqual(x, -extra_width)
            self.assertLessEqual(x, 0.0)
            self.assertGreaterEqual(y, -extra_height)
            self.assertLessEqual(y, 0.0)

    def test_visual_sequence_crossfade_keeps_exact_narration_duration(self):
        from PIL import Image
        from classes.youtube_composer import concatenate_visual_sequence
        from classes.youtube_composer import create_image_sequence

        media_dir = PROJECT_ROOT / ".mp"
        media_dir.mkdir(exist_ok=True)
        image_paths = []
        for index in range(3):
            image_path = media_dir / f"youtube-crossfade-source-{index}.png"
            Image.new("RGB", (1080, 1920), color=(30, 40 + index * 30, 60)).save(image_path)
            image_paths.append(str(image_path))

        clips = create_image_sequence(image_paths, duration=3.0, fps=12)
        base_clip = None
        try:
            base_clip = concatenate_visual_sequence(clips, duration=3.0, fps=12)
            self.assertAlmostEqual(base_clip.duration, 3.0, places=2)
            frame = base_clip.get_frame(1.5)
            self.assertEqual(frame.shape[0], 1920)
            self.assertEqual(frame.shape[1], 1080)
        finally:
            if base_clip is not None:
                base_clip.close()
            for clip in clips:
                clip.close()


if __name__ == "__main__":
    unittest.main()
