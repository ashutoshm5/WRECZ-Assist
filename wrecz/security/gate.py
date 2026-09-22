import json
import os
import threading
from datetime import datetime

from core.prompt import ask_confirmation
from core.settings import SETTINGS
from security.logger import ActivityLogger


STATE_FILE = os.path.join(
    os.path.dirname(__file__),
    "security_state.json"
)


class SecurityCore:

    def __init__(self):

        self._lock = threading.Lock()

        # Activity Logger
        self.logger = ActivityLogger()

        # Internet is ALWAYS OFF when Wrecz starts.
        self.internet_enabled = False

        self.session_started = datetime.now()

        self._write_state()

        # Log Security Core startup.
        self.logger.system_event(
            "SECURITY_CORE_STARTED",
            "Wrecz Security Core initialized."
        )


    # =========================================================
    # STATE FILE
    # =========================================================

    def _write_state(self):

        state = {
            "internet_enabled": self.internet_enabled,

            "session_started":
                self.session_started.isoformat(),

            "last_changed":
                datetime.now().isoformat()
        }


        try:

            with open(
                STATE_FILE,
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    state,
                    file,
                    indent=4
                )


        except Exception as error:

            print(
                "[SECURITY WARNING] "
                f"Could not write security state: {error}"
            )


    # =========================================================
    # CHECK INTERNET STATUS
    # =========================================================

    def is_internet_enabled(self):

        with self._lock:

            return self.internet_enabled


    # =========================================================
    # GET SECURITY STATUS
    # =========================================================

    def get_status(self):

        with self._lock:

            return {
                "internet_enabled":
                    self.internet_enabled,

                "status":
                    (
                        "ONLINE"
                        if self.internet_enabled
                        else "OFFLINE"
                    )
            }


    # =========================================================
    # ENABLE INTERNET
    # =========================================================

    def enable_internet(
        self,
        source="manual"
    ):

        with self._lock:

            self.internet_enabled = True

            self._write_state()


        print(
            f"[SECURITY] Internet ENABLED "
            f"(source: {source})"
        )


        # LOG THE CHANGE
        self.logger.internet_change(
            enabled=True,
            source=source,
            reason="Internet access enabled."
        )


        return True


    # =========================================================
    # DISABLE INTERNET
    # =========================================================

    def disable_internet(
        self,
        source="manual"
    ):

        with self._lock:

            self.internet_enabled = False

            self._write_state()


        print(
            f"[SECURITY] Internet DISABLED "
            f"(source: {source})"
        )


        # LOG THE CHANGE
        self.logger.internet_change(
            enabled=False,
            source=source,
            reason="Internet access disabled."
        )


        return True


    # =========================================================
    # TOGGLE INTERNET
    # =========================================================

    def toggle_internet(self):

        with self._lock:

            self.internet_enabled = (
                not self.internet_enabled
            )

            self._write_state()

            current_state = (
                self.internet_enabled
            )


        print(
            "[SECURITY] Internet "
            + (
                "ENABLED"
                if current_state
                else "DISABLED"
            )
            + " (manual toggle)"
        )


        # LOG TOGGLE
        self.logger.internet_change(
            enabled=current_state,
            source="manual_toggle",
            reason=(
                "Internet state changed "
                "using manual toggle."
            )
        )


        return current_state


    # =========================================================
    # STARTUP PERMISSION
    # =========================================================

    def startup_permission(self):

        print()

        print(
            "=" * 55
        )

        print(
            "              WRECZ SECURITY CORE"
        )

        print(
            "=" * 55
        )

        print()

        print(
            "Internet access is currently DISABLED."
        )

        print()

        print(
            "Enable internet services for this session?"
        )

        print()

        print(
            "  [Y] Enable"
        )

        print(
            "  [N] Keep disabled"
        )

        print()


        answer = input(
            "Choice [N]: "
        ).strip().lower()


        if answer == "y":

            self.enable_internet(
                source="startup"
            )

        else:

            self.disable_internet(
                source="startup"
            )


        print()


    # =========================================================
    # INTERNET PERMISSION GATE
    # =========================================================

    def check_internet(
        self,
        reason=""
    ):

        already_enabled = self.is_internet_enabled()


        # ---------------------------------------------
        # "Ask before web access" OFF - proceed
        # ---------------------------------------------
        #
        # This is what the Settings toggle says on the tin: with it off,
        # a web action is carried out instead of interrupting the user.
        #
        # The session still STARTS offline - the invariant in reset_session
        # is untouched. The first web action is what turns internet on, it
        # is logged with its own source, the tray goes green, and the kill
        # switch still applies. Turning the toggle on restores a prompt
        # before every web action.
        # ---------------------------------------------

        if not SETTINGS.ask_before_web:

            if not already_enabled:

                self.enable_internet(
                    source="web_action"
                )


            print(
                "[SECURITY] Internet request ALLOWED."
            )


            self.logger.security_decision(
                action="internet_access",

                target="internet",

                decision="ALLOWED",

                reason=(
                    reason
                    or
                    "Web action allowed without prompting "
                    "(ask_before_web is off)."
                ),

                internet="ON"
            )


            return True


        # ---------------------------------------------
        # Permission required
        # ---------------------------------------------

        print()

        if already_enabled:

            print(
                "[SECURITY] Internet request needs confirmation."
            )

        else:

            print(
                "[SECURITY] Internet request BLOCKED."
            )


        if reason:

            print(
                f"[SECURITY] Reason: {reason}"
            )


        print()


        if already_enabled:

            question = (
                "Allow WRECZ to use internet access "
                "for this request?"
            )

        else:

            question = (
                "Allow internet access "
                "for this session?"
            )


        allowed = ask_confirmation(
            kind="internet",

            question=question,

            action="internet_access",

            target="internet",

            reason=reason
        )


        # ---------------------------------------------
        # USER ALLOWED
        # ---------------------------------------------

        if allowed:

            if not already_enabled:

                self.enable_internet(
                    source="security_prompt"
                )


            self.logger.security_decision(
                action="internet_access",

                target="internet",

                decision="ALLOWED",

                reason=(
                    "User granted "
                    "internet permission."
                ),

                internet="ON"
            )


            return True


        # ---------------------------------------------
        # USER DENIED
        # ---------------------------------------------

        self.logger.security_decision(
            action="internet_access",

            target="internet",

            decision="BLOCKED",

            reason=(
                "User denied "
                "internet permission."
            ),

            internet="OFF"
        )


        print(
            "[SECURITY] Request DENIED."
        )


        return False


    # =========================================================
    # EMERGENCY INTERNET OFF
    # =========================================================

    def force_off(self):

        self.disable_internet(
            source="emergency_kill_switch"
        )


        print(
            "[SECURITY] EMERGENCY INTERNET "
            "KILL SWITCH ACTIVATED."
        )


    # =========================================================
    # NEW SESSION
    # =========================================================

    def reset_session(self):

        with self._lock:

            self.internet_enabled = False

            self._write_state()


        self.logger.system_event(
            "SESSION_RESET",

            "New Wrecz session initialized "
            "with internet disabled."
        )


        print(
            "[SECURITY] New session initialized. "
            "Internet OFF."
        )