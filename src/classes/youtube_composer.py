from __future__ import annotations

import math
import os
from collections.abc import Callable, Sequence

from PIL import Image


if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS


SHORTS_ASPECT_RATIO = 9 / 16
SHORTS_FRAME_SIZE = (1080, 1920)
DEFAULT_FPS = 30
DEFAULT_AUDIO_FPS = 44100
DEFAULT_IMAGE_MOTION_ZOOM = 0.035
DEFAULT_IMAGE_TRANSITION_SECONDS = 0.28
DEFAULT_VIDEO_BITRATE = "8000k"
DEFAULT_FFMPEG_PARAMS = ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
DEFAULT_BACKGROUND_FADE_SECONDS = 0.75
DEFAULT_NARRATION_TARGET_PEAK = 0.9
DEFAULT_NARRATION_MAX_GAIN = 3.0
DEFAULT_FINAL_AUDIO_TARGET_PEAK = 0.96
MIN_VISUAL_CLIP_SECONDS = 1.2
MAX_VISUAL_CLIP_SECONDS = 6.5
MAX_VISUAL_CLIPS = 24
DEFAULT_IMAGE_PAN_STRENGTH = 0.55


def audio_duration(audio_path: str) -> float:
    """Return an audio file duration in seconds without leaking a MoviePy handle."""
    from moviepy.editor import AudioFileClip

    clip = AudioFileClip(audio_path)
    try:
        return float(clip.duration)
    finally:
        clip.close()


def _log_info(callback: Callable[[str], None] | None, message: str) -> None:
    if callback:
        callback(message)


def _close_clip(clip) -> None:
    if clip is None:
        return
    close = getattr(clip, "close", None)
    if close:
        try:
            close()
        except Exception:
            pass


def _resize_to_shorts_frame(
    image_clip,
    image_path: str,
    verbose: bool = False,
    info_callback: Callable[[str], None] | None = None,
):
    """Crop an image clip to a 9:16 center crop and resize it to Shorts format."""
    from moviepy.video.fx.all import crop

    if round((image_clip.w / image_clip.h), 4) < SHORTS_ASPECT_RATIO:
        if verbose:
            _log_info(info_callback, f" => Resizing Image: {image_path} to 1080x1920")
        image_clip = crop(
            image_clip,
            width=image_clip.w,
            height=round(image_clip.w / SHORTS_ASPECT_RATIO),
            x_center=image_clip.w / 2,
            y_center=image_clip.h / 2,
        )
    else:
        if verbose:
            _log_info(info_callback, f" => Resizing Image: {image_path} to 1920x1080")
        image_clip = crop(
            image_clip,
            width=round(SHORTS_ASPECT_RATIO * image_clip.h),
            height=image_clip.h,
            x_center=image_clip.w / 2,
            y_center=image_clip.h / 2,
        )
    return image_clip.resize(SHORTS_FRAME_SIZE)


def _effective_transition_seconds(
    duration: float,
    clip_count: int,
    requested_seconds: float = DEFAULT_IMAGE_TRANSITION_SECONDS,
) -> float:
    """Return a transition length that cannot dominate short clips."""
    if clip_count <= 1 or duration <= 0:
        return 0.0
    average_clip_duration = float(duration) / clip_count
    return max(0.0, min(float(requested_seconds), average_clip_duration / 3))


def _select_visual_paths(image_paths: Sequence[str], duration: float) -> list[str]:
    """Build a visual timeline that avoids both flashing and long static holds."""
    paths = [str(path) for path in image_paths]
    if not paths:
        return []
    max_clips_for_duration = max(1, int(math.ceil(float(duration) / MIN_VISUAL_CLIP_SECONDS)))
    base_count = min(len(paths), max_clips_for_duration)
    desired_count = max(
        base_count,
        int(math.ceil(float(duration) / MAX_VISUAL_CLIP_SECONDS)),
    )
    desired_count = min(desired_count, max_clips_for_duration, MAX_VISUAL_CLIPS)
    return [paths[index % len(paths)] for index in range(desired_count)]


def _motion_pan_direction(clip_index: int) -> tuple[float, float]:
    directions = (
        (-1.0, -0.35),
        (1.0, 0.35),
        (-0.35, 1.0),
        (0.35, -1.0),
    )
    return directions[clip_index % len(directions)]


def _motion_position(
    clip_index: int,
    progress: float,
    scale: float,
    pan_strength: float = DEFAULT_IMAGE_PAN_STRENGTH,
) -> tuple[float, float]:
    extra_width = max(0.0, SHORTS_FRAME_SIZE[0] * scale - SHORTS_FRAME_SIZE[0])
    extra_height = max(0.0, SHORTS_FRAME_SIZE[1] * scale - SHORTS_FRAME_SIZE[1])
    direction_x, direction_y = _motion_pan_direction(clip_index)
    sweep = (min(1.0, max(0.0, progress)) * 2.0) - 1.0
    safe_strength = max(0.0, min(float(pan_strength), 0.9))

    def axis_offset(extra: float, direction: float) -> float:
        offset = -(extra / 2) + direction * extra * 0.5 * safe_strength * sweep
        return min(0.0, max(-extra, offset))

    return (
        axis_offset(extra_width, direction_x),
        axis_offset(extra_height, direction_y),
    )


def _apply_subtle_motion(image_clip, clip_index: int, fps: int, motion_zoom: float):
    """Add gentle zoom so static generated images feel less like slides."""
    from moviepy.editor import CompositeVideoClip

    motion_zoom = max(0.0, float(motion_zoom or 0.0))
    if motion_zoom <= 0:
        return image_clip

    duration = max(0.1, float(image_clip.duration or 0.1))
    zoom_in = clip_index % 2 == 0

    def progress_at(t: float) -> float:
        return min(1.0, max(0.0, float(t) / duration))

    def scale_at(t: float) -> float:
        progress = progress_at(t)
        if zoom_in:
            return 1.0 + motion_zoom * progress
        return 1.0 + motion_zoom * (1.0 - progress)

    def centered_position(t: float) -> tuple[float, float]:
        scale = scale_at(t)
        return _motion_position(clip_index, progress_at(t), scale)

    moving_clip = image_clip.resize(scale_at).set_position(centered_position)
    return (
        CompositeVideoClip([moving_clip], size=SHORTS_FRAME_SIZE)
        .set_duration(duration)
        .set_fps(fps)
    )


def create_image_sequence(
    image_paths: Sequence[str],
    duration: float,
    fps: int = DEFAULT_FPS,
    transition_seconds: float = DEFAULT_IMAGE_TRANSITION_SECONDS,
    motion_zoom: float = DEFAULT_IMAGE_MOTION_ZOOM,
    verbose: bool = False,
    info_callback: Callable[[str], None] | None = None,
) -> list:
    """Build repeated image clips long enough to cover the narration duration."""
    from moviepy.editor import ImageClip

    if not image_paths:
        raise ValueError("Cannot compose video because no images were provided.")
    if duration <= 0:
        raise ValueError("Cannot compose video because narration duration is empty.")

    selected_paths = _select_visual_paths(image_paths, duration)
    transition = _effective_transition_seconds(
        duration,
        len(selected_paths),
        requested_seconds=transition_seconds,
    )
    per_image_duration = max(
        (float(duration) + transition * max(0, len(selected_paths) - 1))
        / len(selected_paths),
        0.1,
    )
    clips = []

    for clip_index, image_path in enumerate(selected_paths):
        clip = ImageClip(image_path).set_duration(per_image_duration).set_fps(fps)
        clip = _resize_to_shorts_frame(
            clip,
            image_path,
            verbose=verbose,
            info_callback=info_callback,
        )
        clip = _apply_subtle_motion(
            clip,
            clip_index=clip_index,
            fps=fps,
            motion_zoom=motion_zoom,
        )
        clips.append(clip)

    return clips


def concatenate_visual_sequence(
    image_clips: Sequence,
    duration: float,
    fps: int = DEFAULT_FPS,
    transition_seconds: float = DEFAULT_IMAGE_TRANSITION_SECONDS,
):
    """Concatenate image clips with short crossfades and exact final duration."""
    from moviepy.editor import concatenate_videoclips

    if not image_clips:
        raise ValueError("Cannot compose video because no image clips were provided.")

    transition = _effective_transition_seconds(
        duration,
        len(image_clips),
        requested_seconds=transition_seconds,
    )
    if transition > 0:
        faded_clips = [
            clip if index == 0 else clip.crossfadein(transition)
            for index, clip in enumerate(image_clips)
        ]
        base_clip = concatenate_videoclips(
            faded_clips,
            method="compose",
            padding=-transition,
        )
    else:
        base_clip = concatenate_videoclips(image_clips, method="compose")

    return base_clip.set_duration(duration).set_fps(fps)


def prepare_background_music(
    background_clip,
    duration: float,
    audio_fps: int,
    fade_seconds: float = DEFAULT_BACKGROUND_FADE_SECONDS,
):
    """Loop or trim background music so it covers the narration cleanly."""
    from moviepy.editor import afx

    target_duration = max(0.1, float(duration or 0.1))
    safe_fade = max(0.0, min(float(fade_seconds or 0.0), target_duration / 3))
    background_clip = background_clip.set_fps(audio_fps)
    if getattr(background_clip, "duration", 0) and background_clip.duration < target_duration:
        background_clip = background_clip.fx(afx.audio_loop, duration=target_duration)
    else:
        background_clip = background_clip.subclip(
            0,
            min(float(background_clip.duration or target_duration), target_duration),
        )
    background_clip = background_clip.set_duration(target_duration)
    if safe_fade > 0:
        background_clip = background_clip.audio_fadein(safe_fade).audio_fadeout(safe_fade)
    return background_clip


def _audio_peak_level(audio_clip, samples_per_second: int = 80, max_samples: int = 1200) -> float:
    """Estimate the absolute peak level without decoding the whole audio track."""
    import numpy as np

    duration = float(getattr(audio_clip, "duration", 0) or 0)
    if duration <= 0:
        return 0.0

    sample_count = min(max(16, int(duration * samples_per_second)), max_samples)
    end_time = max(0.0, duration - 0.001)
    times = np.linspace(0, end_time, sample_count)
    try:
        frames = np.asarray(audio_clip.get_frame(times), dtype=float)
    except Exception:
        try:
            frames = np.asarray(
                [audio_clip.get_frame(float(timestamp)) for timestamp in times],
                dtype=float,
            )
        except Exception:
            return 0.0
    if frames.size == 0:
        return 0.0
    finite_frames = frames[np.isfinite(frames)]
    if finite_frames.size == 0:
        return 0.0
    return float(np.max(np.abs(finite_frames)))


def prepare_narration_audio(
    narration_clip,
    audio_fps: int,
    target_peak: float = DEFAULT_NARRATION_TARGET_PEAK,
    max_gain: float = DEFAULT_NARRATION_MAX_GAIN,
):
    """Set narration sample rate and gently normalize it so speech stays forward."""
    from moviepy.editor import afx

    narration_clip = narration_clip.set_fps(audio_fps)
    peak = _audio_peak_level(narration_clip)
    if peak <= 0:
        return narration_clip

    safe_target = max(0.05, min(float(target_peak or DEFAULT_NARRATION_TARGET_PEAK), 0.98))
    gain = safe_target / peak
    if gain > 1:
        gain = min(gain, max(1.0, float(max_gain or DEFAULT_NARRATION_MAX_GAIN)))
    if abs(gain - 1.0) < 0.02:
        return narration_clip
    return narration_clip.fx(afx.volumex, gain)


def limit_audio_peak(
    audio_clip,
    target_peak: float = DEFAULT_FINAL_AUDIO_TARGET_PEAK,
):
    """Attenuate the final mix only when narration plus music would clip."""
    from moviepy.editor import afx

    peak = _audio_peak_level(audio_clip)
    safe_target = max(0.05, min(float(target_peak or DEFAULT_FINAL_AUDIO_TARGET_PEAK), 0.98))
    if peak <= safe_target or peak <= 0:
        return audio_clip
    return audio_clip.fx(afx.volumex, safe_target / peak)


def compose_short_video(
    image_paths: Sequence[str],
    tts_path: str,
    background_music_path: str,
    output_path: str,
    subtitle_clips: Sequence | None = None,
    title_overlay_clip=None,
    threads: int = 2,
    fps: int = DEFAULT_FPS,
    audio_fps: int = DEFAULT_AUDIO_FPS,
    music_volume: float = 0.1,
    music_fade_seconds: float = DEFAULT_BACKGROUND_FADE_SECONDS,
    image_transition_seconds: float = DEFAULT_IMAGE_TRANSITION_SECONDS,
    image_motion_zoom: float = DEFAULT_IMAGE_MOTION_ZOOM,
    video_bitrate: str | None = DEFAULT_VIDEO_BITRATE,
    ffmpeg_params: Sequence[str] | None = None,
    verbose: bool = False,
    info_callback: Callable[[str], None] | None = None,
) -> str:
    """Compose the final vertical video from images, narration, music, and overlays."""
    from moviepy.editor import (
        AudioFileClip,
        CompositeAudioClip,
        CompositeVideoClip,
        afx,
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    tts_clip = AudioFileClip(tts_path)
    image_clips = []
    raw_background_clip = None
    background_clip = None
    narration_clip = None
    raw_composite_audio = None
    composite_audio = None
    base_clip = None
    final_clip = None
    rendered_clip = None

    try:
        image_clips = create_image_sequence(
            image_paths,
            tts_clip.duration,
            fps=fps,
            transition_seconds=image_transition_seconds,
            motion_zoom=image_motion_zoom,
            verbose=verbose,
            info_callback=info_callback,
        )
        base_clip = concatenate_visual_sequence(
            image_clips,
            duration=tts_clip.duration,
            fps=fps,
            transition_seconds=image_transition_seconds,
        )

        narration_clip = prepare_narration_audio(tts_clip, audio_fps=audio_fps)
        raw_background_clip = AudioFileClip(background_music_path)
        background_clip = prepare_background_music(
            raw_background_clip,
            duration=tts_clip.duration,
            audio_fps=audio_fps,
            fade_seconds=music_fade_seconds,
        )
        background_clip = background_clip.fx(afx.volumex, music_volume)
        raw_composite_audio = CompositeAudioClip(
            [narration_clip, background_clip]
        )
        composite_audio = limit_audio_peak(raw_composite_audio)

        final_clip = base_clip.set_audio(composite_audio).set_duration(tts_clip.duration)

        overlay_clips = [final_clip]
        if title_overlay_clip is not None:
            overlay_clips.append(title_overlay_clip)
        overlay_clips.extend(subtitle_clips or [])

        rendered_clip = CompositeVideoClip(overlay_clips).set_fps(fps)
        temp_audiofile = os.path.splitext(output_path)[0] + "-temp-audio.m4a"
        rendered_clip.write_videofile(
            output_path,
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            audio_fps=audio_fps,
            bitrate=video_bitrate,
            preset="medium",
            threads=threads,
            ffmpeg_params=list(ffmpeg_params or DEFAULT_FFMPEG_PARAMS),
            temp_audiofile=temp_audiofile,
            remove_temp=True,
        )
        return output_path
    finally:
        for clip in [
            rendered_clip,
            final_clip,
            base_clip,
            composite_audio,
            raw_composite_audio,
            narration_clip,
            background_clip,
            raw_background_clip,
            tts_clip,
            title_overlay_clip,
            *(subtitle_clips or []),
            *image_clips,
        ]:
            _close_clip(clip)
