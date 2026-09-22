import os
import subprocess
import time


# =========================================================
# WRECZ VERIFICATION CORE
# =========================================================
#
# Verification answers:
#
#     "Did the requested state actually occur?"
#
# Verification NEVER grants permission.
# Verification NEVER executes an action.
#
# APPLICATION CLOSE VERIFICATION IS WINDOW-BASED.
#
# Wrecz does NOT verify:
#
#     "Is chrome.exe still running?"
#
# Instead it verifies:
#
#     "Did the specific Wrecz-owned HWND disappear?"
#
# This prevents Wrecz from treating a manually-opened
# application as something it is responsible for closing.
#
# =========================================================


class VerificationCore:

    def __init__(
        self,
        file_manager=None
    ):

        self.file_manager = file_manager

        # -----------------------------------------------------
        # WRECZ WINDOW MANAGER
        # -----------------------------------------------------

        try:
            from security.window_manager import get_window_manager

            # Must be the same registry skills/apps.py registers into, or
            # open verification can never see the window it is looking for.
            self.window_manager = get_window_manager()

        except Exception:
            self.window_manager = None


    # =========================================================
    # MAIN VERIFICATION ENTRY POINT
    # =========================================================

    def verify(
        self,
        action,
        target,
        result
    ):

        action = str(
            action or ""
        ).strip().lower()

        target = str(
            target or ""
        ).strip()


        # =====================================================
        # APPLICATION VERIFICATION
        # =====================================================

        if action == "open_app":

            return self.verify_open_app(
                target
            )


        if action == "close_app":

            return self.verify_close_app(
                target
            )


        if action == "list_apps":

            return self.verify_list_apps(
                result
            )


        # =====================================================
        # FILE VERIFICATION
        # =====================================================

        if action == "create_file":

            return self.verify_create_file(
                target
            )


        if action == "create_directory":

            return self.verify_create_directory(
                target
            )


        if action == "rename_file":

            return self.verify_rename_file(
                target
            )


        if action == "move_file":

            return self.verify_move_file(
                target
            )


        if action == "delete_file":

            return self.verify_delete_file(
                target
            )


        if action == "search_files":

            return self.verify_search_result(
                result
            )


        if action == "list_files":

            return self.verify_list_result(
                result
            )


        # =====================================================
        # WEB SEARCH
        # =====================================================

        if action == "web_search":

            return self.verify_web_search(
                result
            )


        # =====================================================
        # NO VERIFIER FOR THIS ACTION
        # =====================================================
        #
        # None means "WRECZ cannot check this", which is NOT the same as
        # False, which means "WRECZ checked and the state is wrong".
        #
        # Returning False here is what made volume, brightness, Wi-Fi and
        # Bluetooth announce failure after working correctly: they have no
        # verifier, and the caller read that as a failed verification.
        #
        # Callers must treat None as "executed, unverified".

        return None


    # =========================================================
    # APPLICATION: OPEN
    # =========================================================
    #
    # IMPORTANT:
    #
    # Open verification uses the Wrecz-owned window.
    #
    # We do NOT simply check whether chrome.exe is running,
    # because Chrome may already have been running manually.
    #
    # =========================================================

    def verify_open_app(
        self,
        target
    ):

        if not target:
            return False


        # -----------------------------------------------------
        # Preferred verification:
        # verify the Wrecz-owned window.
        # -----------------------------------------------------

        if self.window_manager is not None:

            try:

                if self.window_manager.verify_open(
                    target
                ):

                    return True

            except Exception:
                pass


        # -----------------------------------------------------
        # Do NOT fall back to process-level verification here.
        #
        # If Wrecz failed to register the window, we should
        # report verification failure rather than accidentally
        # claiming that an already-running application was
        # opened by Wrecz.
        # -----------------------------------------------------

        return False


    # =========================================================
    # APPLICATION: CLOSE
    # =========================================================
    #
    # CRITICAL SECURITY RULE:
    #
    # NEVER check:
    #
    #     "Is chrome.exe still running?"
    #
    # because the user may have another Chrome window open.
    #
    # Instead:
    #
    #     Wrecz-owned HWND
    #              ↓
    #     WM_CLOSE
    #              ↓
    #     verify THAT HWND disappeared
    #
    # =========================================================

    def verify_close_app(
        self,
        target
    ):

        if not target:
            return False


        if self.window_manager is None:

            return False


        try:

            return self.window_manager.verify_closed(
                target,
                timeout=8.0
            )

        except Exception:

            return False


    # =========================================================
    # APPLICATION: LIST
    # =========================================================

    def verify_list_apps(
        self,
        result
    ):

        if not isinstance(
            result,
            list
        ):

            return False


        return True


    # =========================================================
    # RESOLVE APPLICATION
    # =========================================================
    #
    # Retained for compatibility with existing code.
    #
    # Verification does NOT use this for close verification.
    #
    # =========================================================

    def resolve_application_executable(
        self,
        target
    ):

        try:

            from security.application_discovery import (
                ApplicationDiscovery
            )


            discovery = (
                ApplicationDiscovery()
            )


            candidates = (
                discovery.discover(
                    target
                )
            )


            if not candidates:

                return None


            # -------------------------------------------------
            # Only consider existing executable candidates.
            # -------------------------------------------------

            valid_candidates = []


            for candidate in candidates:

                executable = getattr(
                    candidate,
                    "executable",
                    ""
                )


                if not executable:

                    continue


                if not os.path.isfile(
                    executable
                ):

                    continue


                if not executable.lower().endswith(
                    ".exe"
                ):

                    continue


                valid_candidates.append(
                    candidate
                )


            if not valid_candidates:

                return None


            # -------------------------------------------------
            # Highest discovery score first.
            # -------------------------------------------------

            valid_candidates.sort(

                key=lambda candidate:

                    getattr(
                        candidate,
                        "score",
                        0
                    ),

                reverse=True
            )


            return (
                valid_candidates[0].executable
            )


        except Exception:

            return None


    # =========================================================
    # PROCESS CHECK
    # =========================================================
    #
    # Retained only for backwards compatibility.
    #
    # IMPORTANT:
    #
    # This function MUST NOT be used to verify close_app.
    #
    # =========================================================

    def process_running(
        self,
        process_name
    ):

        if not process_name:

            return False


        process_name = (
            process_name.lower()
        )


        try:

            output = (
                subprocess.check_output(

                    [
                        "tasklist",
                        "/FO",
                        "CSV",
                        "/NH"
                    ],

                    text=True,

                    stderr=subprocess.DEVNULL
                )
            )


        except Exception:

            return False


        # -----------------------------------------------------
        # CSV parsing without external dependencies.
        # -----------------------------------------------------

        for line in output.splitlines():

            line = line.strip()


            if not line:

                continue


            first_field = (
                line.split(
                    '","',
                    1
                )[0]
                .strip('"')
                .lower()
            )


            if first_field == process_name:

                return True


        return False


    # =========================================================
    # FILE: CREATE
    # =========================================================

    def verify_create_file(
        self,
        target
    ):

        if not target:

            return False


        try:

            return os.path.isfile(
                os.path.abspath(
                    os.path.expandvars(
                        target
                    )
                )
            )


        except Exception:

            return False


    # =========================================================
    # DIRECTORY: CREATE
    # =========================================================

    def verify_create_directory(
        self,
        target
    ):

        if not target:

            return False


        try:

            return os.path.isdir(
                os.path.abspath(
                    os.path.expandvars(
                        target
                    )
                )
            )


        except Exception:

            return False


    # =========================================================
    # FILE: RENAME
    # =========================================================

    def verify_rename_file(
        self,
        target
    ):

        parts = target.split(
            "|",
            1
        )


        if len(parts) != 2:

            return False


        source = parts[0].strip()

        destination = parts[1].strip()


        try:

            source_path = os.path.abspath(
                os.path.expandvars(
                    source
                )
            )


            destination_path = os.path.abspath(
                os.path.expandvars(
                    destination
                )
            )


            return (

                not os.path.exists(
                    source_path
                )

                and

                os.path.exists(
                    destination_path
                )
            )


        except Exception:

            return False


    # =========================================================
    # FILE: MOVE
    # =========================================================

    def verify_move_file(
        self,
        target
    ):

        parts = target.split(
            "|",
            1
        )


        if len(parts) != 2:

            return False


        source = parts[0].strip()

        destination = parts[1].strip()


        try:

            source_path = os.path.abspath(
                os.path.expandvars(
                    source
                )
            )


            destination_path = os.path.abspath(
                os.path.expandvars(
                    destination
                )
            )


            return (

                not os.path.exists(
                    source_path
                )

                and

                os.path.exists(
                    destination_path
                )
            )


        except Exception:

            return False


    # =========================================================
    # FILE: DELETE
    # =========================================================

    def verify_delete_file(
        self,
        target
    ):

        if not target:

            return False


        try:

            path = os.path.abspath(
                os.path.expandvars(
                    target
                )
            )


            return not os.path.exists(
                path
            )


        except Exception:

            return False


    # =========================================================
    # FILE SEARCH
    # =========================================================

    def verify_search_result(
        self,
        result
    ):

        # An empty search result is still a valid search.

        return isinstance(
            result,
            list
        )


    # =========================================================
    # FILE LIST
    # =========================================================

    def verify_list_result(
        self,
        result
    ):

        return isinstance(
            result,
            list
        )


    # =========================================================
    # WEB SEARCH
    # =========================================================

    def verify_web_search(
        self,
        result
    ):

        if result is None:

            return False


        if isinstance(
            result,
            str
        ):

            return bool(
                result.strip()
            )


        if isinstance(
            result,
            list
        ):

            return True


        if isinstance(
            result,
            dict
        ):

            return True


        return False