import os
import re
import subprocess
import uuid

try:
    import soundfile as sf
except ImportError:
    sf = None

try:
    from kittentts import KittenTTS as KittenModel
except ImportError:
    KittenModel = None

try:
    from gtts import gTTS
except ImportError:
    gTTS = None

try:
    from moviepy.editor import AudioFileClip
except ImportError:
    AudioFileClip = None

from config import ROOT_DIR, get_tts_voice

KITTEN_MODEL = "KittenML/kitten-tts-mini-0.8"
KITTEN_SAMPLE_RATE = 24000

class TTS:
    def __init__(self) -> None:
        self._model = KittenModel(KITTEN_MODEL) if KittenModel is not None else None
        self._voice = get_tts_voice()

    def synthesize(self, text, output_file=os.path.join(ROOT_DIR, ".mp", "audio.wav")):
        if self._should_use_korean_tts(text):
            return self._synthesize_korean(text, output_file)

        if self._model is not None and sf is not None:
            audio = self._model.generate(text, voice=self._voice)
            sf.write(output_file, audio, KITTEN_SAMPLE_RATE)
            return output_file

        escaped_text = (
            str(text)
            .replace("`", "")
            .replace('"', '`"')
        )
        temp_output = output_file or os.path.join(
            ROOT_DIR, ".mp", f"{uuid.uuid4()}.wav"
        )
        powershell_script = (
            "Add-Type -AssemblyName System.Speech; "
            "$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f'$speak.SetOutputToWaveFile("{temp_output}"); '
            f'$speak.Speak("{escaped_text}"); '
            "$speak.Dispose();"
        )
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                powershell_script,
            ],
            check=True,
        )
        return output_file

    def _should_use_korean_tts(self, text: str) -> bool:
        """
        Detects Korean text so it can use a Korean-capable TTS backend.
        """
        return bool(re.search(r"[가-힣]", str(text)))

    def _synthesize_korean(self, text: str, output_file: str) -> str:
        """
        Synthesizes Korean speech using Google Translate TTS and converts it to WAV.
        """
        if gTTS is None:
            raise RuntimeError("Korean TTS requires the 'gTTS' package.")
        if AudioFileClip is None:
            raise RuntimeError("Korean TTS conversion requires moviepy.")

        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        temp_mp3 = os.path.splitext(output_file)[0] + ".mp3"
        gTTS(text=str(text), lang="ko").save(temp_mp3)

        audio_clip = AudioFileClip(temp_mp3)
        try:
            audio_clip.write_audiofile(output_file, fps=44100, verbose=False, logger=None)
        finally:
            audio_clip.close()

        try:
            os.remove(temp_mp3)
        except OSError:
            pass

        return output_file
