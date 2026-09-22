from dataclasses import dataclass


@dataclass
class SafetyDecision:

    allowed: bool
    requires_confirmation: bool
    risk_level: str
    reason: str


class ActionSafety:

    # =========================================================
    # SAFE ACTIONS
    # =========================================================

    SAFE_ACTIONS = {

        # Files
        "list_files",
        "search_files",

        # Applications
        "list_apps",
        "open_app",

        # Internet
        "web_search",

        # Not actions at all - they only return text to the user. They are
        # listed so evaluate() does not refuse them as UNKNOWN.
        "clarification",
        "conversation",
        "unsupported"
    }


    # =========================================================
    # REVERSIBLE ACTIONS
    # =========================================================

    REVERSIBLE_ACTIONS = {

        # Window control
        "switch_window",
        "minimize_window",
        "maximize_window",
        "move_window",

        # System controls
        "volume_control",
        "brightness_control",
        "wifi_control",
        "bluetooth_control"
    }


    # =========================================================
    # MODIFYING ACTIONS
    # =========================================================

    MODIFYING_ACTIONS = {

        # Files
        "create_file",
        "create_directory",
        "rename_file",
        "move_file",

        # Application interaction
        "type_text",
        "save_file"
    }


    # =========================================================
    # DESTRUCTIVE ACTIONS
    # =========================================================

    DESTRUCTIVE_ACTIONS = {

        # Files
        "delete_file",
        "delete_directory",

        # Applications
        "close_app",

        # System
        "shutdown",
        "restart",
        "format_drive"
    }


    # =========================================================
    # BLOCKED ACTIONS
    # =========================================================

    BLOCKED_ACTIONS = {

        "modify_registry",
        "disable_security",
        "run_unknown_executable",
        "change_firewall",
        "change_system_permissions"
    }


    # =========================================================
    # CLASSIFY
    # =========================================================

    def classify(
        self,
        action
    ):

        if action in self.BLOCKED_ACTIONS:

            return "BLOCKED"


        if action in self.DESTRUCTIVE_ACTIONS:

            return "DESTRUCTIVE"


        if action in self.MODIFYING_ACTIONS:

            return "MODIFYING"


        if action in self.REVERSIBLE_ACTIONS:

            return "REVERSIBLE"


        if action in self.SAFE_ACTIONS:

            return "SAFE"


        return "UNKNOWN"


    # =========================================================
    # EVALUATE
    # =========================================================

    def evaluate(
        self,
        action,
        target=""
    ):

        risk = self.classify(
            action
        )


        # -----------------------------------------------------
        # BLOCKED
        # -----------------------------------------------------

        if risk == "BLOCKED":

            return SafetyDecision(

                allowed=False,

                requires_confirmation=False,

                risk_level="BLOCKED",

                reason=(
                    "This action is blocked by "
                    "Wrecz Security Policy."
                )
            )


        # -----------------------------------------------------
        # DESTRUCTIVE
        # -----------------------------------------------------

        if risk == "DESTRUCTIVE":

            return SafetyDecision(

                allowed=True,

                requires_confirmation=True,

                risk_level="DESTRUCTIVE",

                reason=(
                    "This action can cause "
                    "destructive or irreversible changes."
                )
            )


        # -----------------------------------------------------
        # MODIFYING
        # -----------------------------------------------------

        if risk == "MODIFYING":

            return SafetyDecision(

                allowed=True,

                requires_confirmation=True,

                risk_level="MODIFYING",

                reason=(
                    "This action modifies user "
                    "data or application state."
                )
            )


        # -----------------------------------------------------
        # REVERSIBLE
        # -----------------------------------------------------

        if risk == "REVERSIBLE":

            return SafetyDecision(

                allowed=True,

                requires_confirmation=False,

                risk_level="REVERSIBLE",

                reason=(
                    "This action is considered "
                    "reversible."
                )
            )


        # -----------------------------------------------------
        # SAFE
        # -----------------------------------------------------

        if risk == "SAFE":

            return SafetyDecision(

                allowed=True,

                requires_confirmation=False,

                risk_level="SAFE",

                reason=(
                    "This is a read-only or "
                    "low-risk action."
                )
            )


        # -----------------------------------------------------
        # UNKNOWN
        # -----------------------------------------------------

        return SafetyDecision(

            allowed=False,

            requires_confirmation=False,

            risk_level="UNKNOWN",

            reason=(
                "Wrecz does not have a defined "
                "security policy for this action."
            )
        )