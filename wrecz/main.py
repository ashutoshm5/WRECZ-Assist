# Preload PyTorch before Wrecz's WinRT-based modules.
# This avoids the Windows c10.dll initialization conflict without changing
# any existing Wrecz functionality.
import torch

from core.brain import ask_wrecz
from core.response import respond
from core.router import Router
from security.gate import SecurityCore
from security.tray import SecurityTray

from voice import VoiceEngine


def main():

    print()
    print("========================================")
    print("             W R E C Z")
    print("       Local AI PC Assistant")
    print("========================================")
    print()


    # =====================================================
    # SECURITY CORE
    # =====================================================

    security = SecurityCore()

    # Always start the session with internet OFF.
    security.reset_session()


    # =====================================================
    # STARTUP INTERNET PROMPT
    # =====================================================

    security.startup_permission()


    # =====================================================
    # SECURITY TRAY
    # =====================================================

    tray = SecurityTray(
        security
    )

    tray.start()


    # =====================================================
    # ROUTER
    # =====================================================

    router = Router(
        security
    )

    # =====================================================
    # VOICE OUTPUT
    # =====================================================
    # Kokoro is loaded lazily. Existing WRECZ startup and
    # security behavior remain unchanged.
    voice = VoiceEngine(
        voice="am_fenrir",
        speed=0.94,
    )

    # Preload Kokoro once so the first spoken response starts faster.
    try:
        voice.warm_up()
    except Exception as voice_error:
        print(
            "[VOICE]",
            f"TTS warm-up unavailable: {voice_error}"
        )


    print("Wrecz Security Core: READY")

    if security.is_internet_enabled():

        print(
            "Internet: ENABLED"
        )

    else:

        print(
            "Internet: DISABLED"
        )


    print()
    print(
        "Wrecz is ready."
    )

    print(
        "Type 'status' to check security."
    )

    print(
        "Type 'internet on' or "
        "'internet off' for manual control."
    )

    print(
        "Type 'exit' to shut down."
    )

    print()


    # =====================================================
    # MAIN LOOP
    # =====================================================

    while True:

        try:

            user_input = input(
                "You: "
            ).strip()


            if not user_input:

                continue


            # -------------------------------------------------
            # EXIT
            # -------------------------------------------------

            if user_input.lower() in [
                "exit",
                "quit",
                "bye"
            ]:

                print()
                print(
                    "Wrecz shutting down."
                )

                break


            # -------------------------------------------------
            # SECURITY STATUS
            # -------------------------------------------------

            if user_input.lower() == "status":

                status = security.get_status()

                print()

                print(
                    "========== SECURITY STATUS =========="
                )

                print(
                    f"Internet: "
                    f"{status['status']}"
                )

                print(
                    "====================================="
                )

                print()

                continue


            # -------------------------------------------------
            # MANUAL INTERNET ON
            # -------------------------------------------------

            if user_input.lower() in [
                "internet on",
                "enable internet",
                "turn internet on"
            ]:

                security.enable_internet(
                    source="manual_command"
                )

                tray.refresh()

                continue


            # -------------------------------------------------
            # MANUAL INTERNET OFF
            # -------------------------------------------------

            if user_input.lower() in [
                "internet off",
                "disable internet",
                "turn internet off"
            ]:

                security.force_off()

                tray.refresh()

                continue


            # -------------------------------------------------
            # ASK LOCAL BRAIN
            # -------------------------------------------------

            security.logger.user_command(user_input)

            command = ask_wrecz(
                user_input
            )

            security.logger.brain_decision(user_input, command)


            print()
            print(
                "[BRAIN]"
            )

            print(
                command
            )

            print()


            # -------------------------------------------------
            # ROUTE COMMAND + GENERIC VOICE OUTPUT
            # -------------------------------------------------
            # Normal conversation is answered directly by Phi.
            # Existing action commands continue through Router exactly as before.
            if command.get("action") == "conversation":
                result = str(
                    command.get("response", "")
                ).strip()
            else:
                result = respond(
                    command,
                    router.execute(command)
                )

            if result:
                try:
                    voice.speak(
                        str(result)
                    )
                except Exception as voice_error:
                    print(
                        "[VOICE]",
                        f"TTS unavailable: {voice_error}"
                    )

            print()
            print(
                "Wrecz:",
                result
            )

            print()

            # Update tray after action
            tray.refresh()


        except KeyboardInterrupt:

            print()
            print(
                "\nWrecz shutting down."
            )

            break


        except Exception as error:

            print()
            print(
                "[ERROR]",
                error
            )

            print()


if __name__ == "__main__":

    main()