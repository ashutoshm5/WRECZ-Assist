DEFAULT_VOICE = "am_fenrir"
DEFAULT_SPEED = 0.94

# WRECZ pronunciation target:
# "wraekkkzzzz"
#
# This is installed directly into Misaki's lexicon so the spelling
# shown to the user/code remains WRECZ while Kokoro receives the
# intended pronunciation override.
WRECZ_PHONEMES = "waekze"

# Playback is written in slices rather than whole sentences so an audio
# listener is driven at roughly 21ms intervals instead of once per sentence.
SLICE_SAMPLES = 512


class KokoroVoice:
    def __init__(
        self,
        voice=DEFAULT_VOICE,
        speed=DEFAULT_SPEED,
    ):
        self.voice = voice
        self.speed = speed
        self._pipeline = None
        self._pronunciation_installed = False

    def _get_pipeline(self):
        if self._pipeline is None:
            from kokoro import KPipeline

            self._pipeline = KPipeline(
                lang_code="a"
            )

        if not self._pronunciation_installed:
            lexicon = getattr(
                self._pipeline.g2p,
                "lexicon",
                None,
            )

            if lexicon is None or not hasattr(
                lexicon,
                "golds",
            ):
                raise RuntimeError(
                    "Kokoro/Misaki does not expose "
                    "g2p.lexicon.golds."
                )

            lexicon.golds["wrecz"] = WRECZ_PHONEMES
            self._pronunciation_installed = True

        return self._pipeline

    def warm_up(self):
        """Load Kokoro once so the first response does not pay model-load latency."""
        self._get_pipeline()
        return True

    def speak(self, text, on_audio=None):
        """Generate Kokoro audio chunks and play them as they are produced.

        No WAV or other temporary audio file is created.

        on_audio, when given, receives each slice of audio as
        (samples, sample_rate) immediately before that slice is written to the
        speakers. Kokoro emits a whole sentence at a time, so playback is
        written in small slices: stream.write blocks until the device accepts
        the audio, which paces the callback to real time. That is what keeps a
        visualizer in step with what is actually being heard.
        """
        if not text or not text.strip():
            raise ValueError(
                "Text cannot be empty."
            )

        import numpy as np
        import sounddevice as sd

        pipeline = self._get_pipeline()

        sample_rate = 24000
        stream = sd.OutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            latency="low",
        )

        try:
            stream.start()

            produced_audio = False

            for _, _, audio in pipeline(
                text,
                voice=self.voice,
                speed=self.speed,
            ):
                chunk = np.asarray(
                    audio,
                    dtype=np.float32,
                ).reshape(-1)

                if chunk.size == 0:
                    continue

                produced_audio = True

                for start in range(
                    0,
                    chunk.size,
                    SLICE_SAMPLES,
                ):
                    piece = chunk[
                        start:start + SLICE_SAMPLES
                    ]

                    if on_audio is not None:
                        # A failing listener must never break speech.
                        try:
                            on_audio(
                                piece,
                                sample_rate,
                            )
                        except Exception as error:
                            print(
                                "[VOICE] Audio listener failed, "
                                f"detaching: {error}"
                            )
                            on_audio = None

                    stream.write(
                        piece.reshape(-1, 1)
                    )

            if not produced_audio:
                raise RuntimeError(
                    "Kokoro produced no audio."
                )

        finally:
            stream.stop()
            stream.close()

        return True
