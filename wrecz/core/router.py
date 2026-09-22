from skills.apps import open_app
from skills.internet import google_search
from skills.files import FileManager

from skills.system.wifi import (
    get_wifi_status,
    enable_wifi,
    disable_wifi
)

from skills.system.bluetooth import (
    get_bluetooth_status,
    enable_bluetooth,
    disable_bluetooth
)

from skills.system.volume import (
    set_volume,
    increase_volume,
    decrease_volume,
    mute,
    unmute
)

from skills.system.brightness import (
    set_brightness,
    increase_brightness,
    decrease_brightness
)

from core.executor import ActionExecutor
from core.prompt import ask_confirmation
from core.settings import SETTINGS

from security.policy import SecurityPolicy
from security.safety import ActionSafety
from security.verification import VerificationCore
from security.window_manager import get_window_manager


class Router:

    def __init__(
        self,
        security
    ):

        self.security = security

        self.logger = security.logger

        self.file_manager = FileManager()

        self.policy = SecurityPolicy()

        # Shared with skills/apps.py and VerificationCore: a window
        # registered by one must be visible to the others.
        self.window_manager = get_window_manager()

        # Risk classification for every action, not just filesystem ones.
        self.safety = ActionSafety()

        # "Did the requested state actually occur?" Never grants permission
        # and never executes anything.
        self.verifier = VerificationCore(
            file_manager=self.file_manager
        )

        # Runs an operation, logs its lifecycle, and verifies the outcome.
        self.executor = ActionExecutor(
            logger=self.logger,
            verifier=self.verifier
        )


    # =========================================================
    # MAIN COMMAND ROUTER
    # =========================================================

    def execute(
        self,
        command
    ):

        action = command.get(
            "action",
            "unsupported"
        )

        target = command.get(
            "target",
            ""
        )

        internet = command.get(
            "internet",
            "NO"
        )

        confirmation = command.get(
            "confirmation",
            "NO"
        )

        reason = command.get(
            "reason",
            ""
        )


        # =====================================================
        # SAFETY CLASSIFICATION
        # =====================================================
        #
        # Runs before anything else so the risk level is recorded even for
        # actions that never reach execution.
        # =====================================================

        safety = self.safety.evaluate(
            action,
            target
        )


        self.logger.action_planned(
            action=action,
            target=target,
            risk_level=safety.risk_level,
            reason=safety.reason
        )


        if not safety.allowed:

            self.logger.action_result(
                action=action,
                target=target,
                result=safety.reason,
                success=False,
                reason=(
                    "Blocked by Wrecz safety policy "
                    f"({safety.risk_level})."
                )
            )


            return safety.reason


        # =====================================================
        # LOCAL ACTIONS
        # =====================================================

        local_actions = {

            "open_app",
            "close_app",

            "volume_control",
            "brightness_control",

            "wifi_control",
            "bluetooth_control",

            "list_files",
            "search_files",
            "create_file",
            "create_directory",
            "rename_file",
            "move_file",
            "delete_file"
        }


        # =====================================================
        # HARD INTERNET BOUNDARY
        # =====================================================

        if action in local_actions:

            internet = "NO"


        # =====================================================
        # INTERNET SECURITY GATE
        # =====================================================

        if (
            action == "web_search"
            and
            internet == "REQUEST"
        ):

            allowed = (
                self.security.check_internet(
                    reason=(
                        reason
                        or
                        "Web search requires internet access."
                    )
                )
            )


            if not allowed:

                self.logger.action_result(

                    action=action,

                    target=target,

                    result=(
                        "Action blocked by "
                        "internet security."
                    ),

                    success=False,

                    reason=(
                        "Internet permission denied."
                    )
                )


                return (
                    "Internet access was denied. "
                    "The action was blocked."
                )


        # =====================================================
        # FILE ACTIONS
        # =====================================================

        file_actions = {

            "list_files",
            "search_files",
            "create_file",
            "create_directory",
            "rename_file",
            "move_file",
            "delete_file"
        }


        # =====================================================
        # GENERIC CONFIRMATION
        # =====================================================

        # ActionSafety is the authority on whether an action needs
        # confirming. The brain's own confirmation flag is still honoured, so
        # a command can ask for confirmation the risk model would not.
        needs_confirmation = (
            safety.requires_confirmation
            or
            confirmation == "YES"
        )


        if (
            needs_confirmation
            and
            action not in file_actions
            and
            SETTINGS.confirm_destructive
        ):

            print()

            print(
                "[SECURITY] This action requires confirmation."
            )

            print(
                f"[SECURITY] Risk: {safety.risk_level}"
            )

            print(
                f"[SECURITY] Action: {action}"
            )

            print(
                f"[SECURITY] Target: {target}"
            )

            print()


            allowed = ask_confirmation(
                kind="action",

                question=(
                    "Allow this action?"
                ),

                action=action,

                target=target,

                reason=(
                    reason
                    or
                    safety.reason
                ),

                metadata={
                    "risk_level": safety.risk_level
                }
            )


            if not allowed:

                self.logger.confirmation(

                    action=action,

                    target=target,

                    decision="DENIED"
                )


                self.logger.action_result(

                    action=action,

                    target=target,

                    result="Action cancelled.",

                    success=False,

                    reason=(
                        "User denied confirmation."
                    )
                )


                return (
                    "Action cancelled."
                )


            self.logger.confirmation(

                action=action,

                target=target,

                decision="ALLOWED"
            )


        # =====================================================
        # OPEN APPLICATION
        # =====================================================

        if action == "open_app":

            # The executor logs the lifecycle and asks VerificationCore
            # whether a Wrecz-owned window actually appeared.
            outcome = self.executor.execute(
                action=action,
                target=target,
                operation=lambda: open_app(target)
            )


            return outcome["message"]


               # =====================================================
        # CLOSE APPLICATION
        # =====================================================

        if action == "close_app":

            print()

            print(
                "[WINDOW SECURITY]"
            )

            print(
                f"Target : {target}"
            )

            print(
                "Mode   : Verified application window"
            )

            print()


            # -------------------------------------------------
            # Try the Wrecz-owned window first, then an already
            # running verified application window.
            #
            # This preserves the existing ownership model.
            # -------------------------------------------------

            def close_operation():

                success, message = (
                    self.window_manager.close_owned_window(
                        target
                    )
                )

                if success:
                    return success, message

                return (
                    self.window_manager.close_existing_window(
                        target
                    )
                )


            # The executor logs the lifecycle and asks VerificationCore
            # whether the specific window handle actually disappeared.
            outcome = self.executor.execute(
                action=action,
                target=target,
                operation=close_operation
            )


            message = outcome["message"]


            return message


        # =====================================================
        # VOLUME CONTROL
        # =====================================================

        if action == "volume_control":

            # Target arrives as "operation|amount", e.g. "set|50",
            # "increase|10", "decrease|10", or a bare operation like
            # "mute" / "unmute".
            def volume_operation():

                operation, _, amount = target.partition("|")

                operation = operation.strip().lower()

                amount = amount.strip()


                if operation == "set":
                    return set_volume(amount)

                if operation == "increase":
                    return increase_volume(amount or 10)

                if operation == "decrease":
                    return decrease_volume(amount or 10)

                if operation == "mute":
                    return mute()

                if operation == "unmute":
                    return unmute()

                # Fallback: treat the whole target as a plain percentage,
                # for backward compatibility.
                return set_volume(target)


            # The executor catches exceptions, logs the lifecycle, and
            # records this as executed-but-unverifiable: there is no
            # verifier for volume.
            outcome = self.executor.execute(
                action=action,
                target=target,
                operation=volume_operation
            )


            return outcome["message"]


        # =====================================================
        # BRIGHTNESS CONTROL
        # =====================================================

        if action == "brightness_control":

            # Target format mirrors volume: "set|70", "increase|10",
            # "decrease|10".
            def brightness_operation():

                operation, _, amount = target.partition("|")

                operation = operation.strip().lower()

                amount = amount.strip()


                if operation == "set":
                    return set_brightness(amount)

                if operation == "increase":
                    return increase_brightness(amount or 10)

                if operation == "decrease":
                    return decrease_brightness(amount or 10)

                # Backward compatibility: a bare "70" is an absolute
                # brightness percentage.
                return set_brightness(target)


            outcome = self.executor.execute(
                action=action,
                target=target,
                operation=brightness_operation
            )


            return outcome["message"]


        # =====================================================
        # WI-FI CONTROL
        # =====================================================

        if action == "wifi_control":

            def wifi_operation():

                operation = target.strip().lower()


                if operation in {
                    "status",
                    "get",
                    "check",
                    "state"
                }:

                    success, result = get_wifi_status()

                    if not success:
                        return False, result

                    return True, (
                        "Wi-Fi is on."
                        if result.get("enabled", False)
                        else "Wi-Fi is off."
                    )


                if operation in {
                    "on",
                    "enable",
                    "enabled",
                    "turn_on"
                }:
                    return enable_wifi()


                if operation in {
                    "off",
                    "disable",
                    "disabled",
                    "turn_off"
                }:
                    return disable_wifi()


                return False, "Unknown Wi-Fi operation."


            outcome = self.executor.execute(
                action=action,
                target=target,
                operation=wifi_operation
            )


            return outcome["message"]


        # =====================================================
        # BLUETOOTH CONTROL
        # =====================================================

        if action == "bluetooth_control":

            def bluetooth_operation():

                operation = target.strip().lower()


                if operation in {
                    "status",
                    "get",
                    "check",
                    "state"
                }:

                    success, result = get_bluetooth_status()

                    if not success:
                        return False, result

                    return True, (
                        "Bluetooth is on."
                        if result.get("enabled", False)
                        else "Bluetooth is off."
                    )


                if operation in {
                    "on",
                    "enable",
                    "enabled",
                    "turn_on"
                }:
                    return enable_bluetooth()


                if operation in {
                    "off",
                    "disable",
                    "disabled",
                    "turn_off"
                }:
                    return disable_bluetooth()


                return False, "Unknown Bluetooth operation."


            outcome = self.executor.execute(
                action=action,
                target=target,
                operation=bluetooth_operation
            )


            return outcome["message"]


        # =====================================================
        # WEB SEARCH
        # =====================================================

        if action == "web_search":

            if not self.security.is_internet_enabled():

                allowed = (
                    self.security.check_internet(
                        reason=(
                            reason
                            or
                            "Web search requires internet access."
                        )
                    )
                )


                if not allowed:

                    self.logger.action_result(

                        action=action,

                        target=target,

                        result="Web search blocked.",

                        success=False,

                        reason=(
                            "Internet permission denied."
                        )
                    )


                    return (
                        "Web search blocked by "
                        "Wrecz Security."
                    )


            # google_search returns a plain string, which the executor
            # treats as success. It also catches a browser failure, and
            # VerificationCore checks the result actually looks like a
            # search that ran.
            outcome = self.executor.execute(
                action=action,
                target=target,
                operation=lambda: google_search(target)
            )


            return outcome["message"]


        # =====================================================
        # FILE MANAGEMENT
        # =====================================================

        if action in file_actions:

            security_level = (
                self.policy.classify(
                    action
                )
            )


            # -------------------------------------------------
            # BLOCKED
            # -------------------------------------------------

            if security_level == "BLOCKED":

                result = (
                    "This filesystem operation "
                    "is blocked by Wrecz Security."
                )


                self.logger.action_result(

                    action=action,

                    target=target,

                    result=result,

                    success=False,

                    reason=(
                        "Security policy blocked "
                        "the action."
                    )
                )


                return result


            # -------------------------------------------------
            # FILE CONFIRMATION
            # -------------------------------------------------

            if (
                safety.requires_confirmation
                and
                SETTINGS.confirm_destructive
            ):

                print()

                print(
                    "[SECURITY] File operation "
                    "requires confirmation."
                )

                print(
                    f"[SECURITY] Risk: {safety.risk_level}"
                )

                print(
                    f"[SECURITY] Action: {action}"
                )

                print(
                    f"[SECURITY] Target: {target}"
                )

                print()


                allowed = ask_confirmation(
                    kind="file",

                    question=(
                        "Allow this file operation?"
                    ),

                    action=action,

                    target=target,

                    reason=(
                        reason
                        or
                        safety.reason
                    ),

                    metadata={
                        "risk_level": safety.risk_level
                    }
                )


                if not allowed:

                    self.logger.confirmation(

                        action=action,

                        target=target,

                        decision="DENIED"
                    )


                    self.logger.action_result(

                        action=action,

                        target=target,

                        result=(
                            "File operation cancelled."
                        ),

                        success=False,

                        reason=(
                            "User denied confirmation."
                        )
                    )


                    return (
                        "File operation cancelled."
                    )


                self.logger.confirmation(

                    action=action,

                    target=target,

                    decision="ALLOWED"
                )


            # -------------------------------------------------
            # LIST
            # -------------------------------------------------

            # -------------------------------------------------
            # Rename and move need two halves before anything runs.
            # -------------------------------------------------

            if action in {"rename_file", "move_file"}:

                parts = target.split("|", 1)

                if len(parts) != 2:

                    result = (
                        "I need both the original "
                        "and new filename."
                        if action == "rename_file"
                        else
                        "I need both the source "
                        "and destination."
                    )


                    self.logger.action_result(
                        action=action,
                        target=target,
                        result=result,
                        success=False,
                        reason=(
                            f"{action} requires "
                            "source and destination."
                        )
                    )


                    return result


            # -------------------------------------------------
            # DISPATCH
            # -------------------------------------------------

            def file_operation():

                if action == "list_files":
                    return self.file_manager.list_directory(
                        target or "."
                    )

                if action == "search_files":
                    return self.file_manager.search_files(target)

                if action == "create_directory":
                    return self.file_manager.create_directory(target)

                if action == "create_file":
                    return self.file_manager.create_file(target)

                if action == "delete_file":
                    return self.file_manager.delete(target)

                if action in {"rename_file", "move_file"}:

                    source, destination = (
                        piece.strip()
                        for piece in target.split("|", 1)
                    )

                    if action == "rename_file":
                        return self.file_manager.rename(
                            source,
                            destination
                        )

                    return self.file_manager.move(
                        source,
                        destination
                    )


                return False, "Unknown filesystem operation."


            outcome = self.executor.execute(
                action=action,
                target=target,
                operation=file_operation
            )


            result = outcome["message"]


            # -------------------------------------------------
            # A listing comes back as rows, not a sentence.
            # -------------------------------------------------

            if isinstance(result, list):

                if not result:
                    return "No matching files found."


                return "\n".join(
                    f"{item['type']}: {item['path']}"
                    for item in result
                )


            return result


        # =====================================================
        # CLARIFICATION
        # =====================================================

        if action == "clarification":

            result = (
                "I need a little more information "
                "before I can perform that action."
            )


            self.logger.action_result(

                action=action,

                target=target,

                result=result,

                success=False,

                reason=(
                    "User request requires clarification."
                )
            )


            return result


        # =====================================================
        # UNSUPPORTED
        # =====================================================

        if action == "unsupported":

            result = (
                "I understand the request, "
                "but that capability is not enabled yet."
            )


            self.logger.action_result(

                action=action,

                target=target,

                result=result,

                success=False,

                reason=(
                    "Requested capability "
                    "is not implemented."
                )
            )


            return result


        # =====================================================
        # UNKNOWN ACTION
        # =====================================================

        result = (
            "This action is not recognized by "
            "the Wrecz security controller."
        )


        self.logger.action_result(

            action=action,

            target=target,

            result=result,

            success=False,

            reason=(
                "Unknown action reached router."
            )
        )


        return result