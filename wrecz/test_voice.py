from voice import VoiceEngine


if __name__ == "__main__":
    print("Loading WRECZ realtime voice...")

    voice = VoiceEngine(
        voice="am_fenrir",
        speed=0.94,
    )

    voice.speak(
        "Hello. I'm WRECZ. I'm ready when you are."
    )

    print("Realtime voice test complete.")
    print("No audio file was created.")
