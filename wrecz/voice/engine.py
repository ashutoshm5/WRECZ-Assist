from .kokoro import KokoroVoice


class VoiceEngine:
    """Public WRECZ realtime text-to-speech interface."""

    def __init__(self, voice="am_fenrir", speed=0.94):
        self._voice = KokoroVoice(
            voice=voice,
            speed=speed,
        )

    def warm_up(self):
        return self._voice.warm_up()

    def speak(self, text, on_audio=None):
        """Speak text. on_audio, when given, receives each slice of audio as
        (samples, sample_rate) in step with playback."""
        return self._voice.speak(text, on_audio=on_audio)
