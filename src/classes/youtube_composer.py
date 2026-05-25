from __future__ import annotations

import os
from collections.abc import Callable, Sequence


SHORTS_ASPECT_RATIO = 9 / 16
SHORTS_FRAME_SIZE = (1080, 1920)
DEFAULT_FPS = 30
DEFAULT_AUDIO_FPS = 44100


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


def create_image_sequence(
    image_paths: Sequence[str],
    duration: float,
    fps: int = DEFAULT_FPS,
    verbose: bool = False,
    info_callback: Callable[[str], None] | None = None,
) -> list:
    """Build repeated image clips long enough to cover the narration duration."""
    from moviepy.editor import ImageClip

    if not image_paths:
        raise ValueError("Cannot compose video because no images were provided.")
    if duration <= 0:
        raise ValueError("Cannot compose video because narration duration is empty.")

    per_image_duration = max(float(duration) / len(image_paths), 0.1)
    clips = []
    total_duration = 0.0

    while total_duration < duration:
        for image_path in image_paths:
            clip = ImageClip(image_path).set_duration(per_image_duration).set_fps(fps)
            clip = _resize_to_shorts_frame(
                clip,
                image_path,
                verbose=verbose,
                info_callback=info_callback,
            )
            clips.append(clip)
            total_duration += per_image_duration
            if total_duration >= duration:
                break

    return clips


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
    verbose: bool = False,
    info_callback: Callable[[str], None] | None = None,
) -> str:
    """Compose the final vertical video from images, narration, music, and overlays."""
    from moviepy.editor import (
        AudioFileClip,
        CompositeAudioClip,
        CompositeVideoClip,
        afx,
        concatenate_videoclips,
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    tts_clip = AudioFileClip(tts_path)
    image_clips = []
    background_clip = None
    composite_audio = None
    base_clip = None
    final_clip = None
    rendered_clip = None

    try:
        image_clips = create_image_sequence(
            image_paths,
            tts_clip.duration,
            fps=fps,
            verbose=verbose,
            info_callback=info_callback,
        )
        base_clip = concatenate_videoclips(image_clips).set_fps(fps)

        background_clip = AudioFileClip(background_music_path).set_fps(audio_fps)
        background_clip = background_clip.fx(afx.volumex, music_volume)
        composite_audio = CompositeAudioClip(
            [tts_clip.set_fps(audio_fps), background_clip]
        )

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
            preset="medium",
            threads=threads,
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
            background_clip,
            tts_clip,
            title_overlay_clip,
            *(subtitle_clips or []),
            *image_clips,
        ]:
            _close_clip(clip)
