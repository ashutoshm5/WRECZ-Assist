import json
import os
import threading
from datetime import datetime


LOG_DIRECTORY = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "logs"
)


LOG_FILE = os.path.join(
    LOG_DIRECTORY,
    "wrecz_activity.jsonl"
)


class ActivityLogger:

    def __init__(self):

        self._lock = threading.Lock()

        os.makedirs(
            LOG_DIRECTORY,
            exist_ok=True
        )


    # =========================================================
    # CORE LOGGER
    # =========================================================

    def log(
        self,
        event,
        source="system",
        command=None,
        action=None,
        target=None,
        internet=None,
        confirmation=None,
        decision=None,
        result=None,
        reason=None,
        metadata=None
    ):

        entry = {

            "timestamp":
                datetime.now()
                .astimezone()
                .isoformat(),

            "event": event,

            "source": source,

            "command": command,

            "action": action,

            "target": target,

            "internet": internet,

            "confirmation": confirmation,

            "decision": decision,

            "result": result,

            "reason": reason,

            "metadata": metadata or {}
        }


        try:

            with self._lock:

                with open(
                    LOG_FILE,
                    "a",
                    encoding="utf-8"
                ) as file:

                    file.write(
                        json.dumps(
                            entry,
                            ensure_ascii=False
                        )
                        + "\n"
                    )


        except Exception as error:

            print(
                f"[LOGGER ERROR] "
                f"Could not write activity log: {error}"
            )


    # =========================================================
    # USER COMMAND
    # =========================================================

    def user_command(
        self,
        command
    ):

        self.log(

            event="USER_COMMAND",

            source="user",

            command=command
        )


    # =========================================================
    # BRAIN DECISION
    # =========================================================

    def brain_decision(
        self,
        command,
        parsed_command
    ):

        self.log(

            event="BRAIN_DECISION",

            source="wrecz-brain",

            command=command,

            action=parsed_command.get(
                "action"
            ),

            target=parsed_command.get(
                "target"
            ),

            internet=parsed_command.get(
                "internet"
            ),

            confirmation=parsed_command.get(
                "confirmation"
            ),

            reason=parsed_command.get(
                "reason"
            ),

            metadata={

                "intent":
                    parsed_command.get(
                        "intent"
                    )
            }
        )


    # =========================================================
    # SECURITY DECISION
    # =========================================================

    def security_decision(
        self,
        action,
        target,
        decision,
        reason,
        internet=None,
        confirmation=None
    ):

        self.log(

            event="SECURITY_DECISION",

            source="security_core",

            action=action,

            target=target,

            internet=internet,

            confirmation=confirmation,

            decision=decision,

            reason=reason
        )


    # =========================================================
    # ACTION PLANNED
    # =========================================================

    def action_planned(
        self,
        action,
        target,
        risk_level,
        reason=None
    ):

        self.log(

            event="ACTION_PLANNED",

            source="action_safety",

            action=action,

            target=target,

            decision=risk_level,

            reason=reason,

            metadata={

                "stage": "planning",

                "risk_level":
                    risk_level
            }
        )


    # =========================================================
    # ACTION STARTED
    # =========================================================

    def action_started(
        self,
        action,
        target
    ):

        self.log(

            event="ACTION_STARTED",

            source="action_engine",

            action=action,

            target=target,

            decision="STARTED",

            metadata={

                "stage": "execution"
            }
        )


    # =========================================================
    # ACTION EXECUTED
    # =========================================================

    def action_executed(
        self,
        action,
        target,
        result=None
    ):

        self.log(

            event="ACTION_EXECUTED",

            source="action_engine",

            action=action,

            target=target,

            decision="EXECUTED",

            result=result,

            metadata={

                "stage": "execution"
            }
        )


    # =========================================================
    # ACTION VERIFIED
    # =========================================================

    def action_verified(
        self,
        action,
        target,
        result=None
    ):

        self.log(

            event="ACTION_VERIFIED",

            source="verification_core",

            action=action,

            target=target,

            decision="VERIFIED",

            result=result,

            metadata={

                "stage": "verification",

                "verified": True
            }
        )


    # =========================================================
    # ACTION VERIFICATION FAILED
    # =========================================================

    def action_verification_failed(
        self,
        action,
        target,
        result=None
    ):

        self.log(

            event="ACTION_VERIFICATION_FAILED",

            source="verification_core",

            action=action,

            target=target,

            decision="VERIFICATION_FAILED",

            result=result,

            reason=(
                "The action executed, "
                "but the expected result "
                "could not be verified."
            ),

            metadata={

                "stage": "verification",

                "verified": False
            }
        )


    # =========================================================
    # ACTION RESULT
    # =========================================================

    def action_result(
        self,
        action,
        target,
        result,
        success,
        reason=None
    ):

        self.log(

            event="ACTION_RESULT",

            source="action_engine",

            action=action,

            target=target,

            result=result,

            decision=(

                "SUCCESS"

                if success

                else "FAILED"
            ),

            reason=reason
        )


    # =========================================================
    # INTERNET STATE CHANGE
    # =========================================================

    def internet_change(
        self,
        enabled,
        source,
        reason=None
    ):

        self.log(

            event="INTERNET_STATE_CHANGE",

            source=source,

            decision=(

                "ENABLED"

                if enabled

                else "DISABLED"
            ),

            result=(

                "INTERNET_ON"

                if enabled

                else "INTERNET_OFF"
            ),

            reason=reason
        )


    # =========================================================
    # CONFIRMATION
    # =========================================================

    def confirmation(
        self,
        action,
        target,
        decision
    ):

        self.log(

            event="CONFIRMATION",

            source="user",

            action=action,

            target=target,

            decision=decision
        )


    # =========================================================
    # SYSTEM EVENT
    # =========================================================

    def system_event(
        self,
        event,
        reason=None
    ):

        self.log(

            event=event,

            source="system",

            reason=reason
        )


    # =========================================================
    # GET LOG FILE
    # =========================================================

    def get_log_file(self):

        return LOG_FILE