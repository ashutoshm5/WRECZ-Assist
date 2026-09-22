class ActionExecutor:

    def __init__(
        self,
        logger,
        verifier
    ):

        self.logger = logger
        self.verifier = verifier


    # =========================================================
    # EXECUTE
    # =========================================================

    def execute(
        self,
        action,
        target="",
        operation=None
    ):

        self.logger.action_started(
            action=action,
            target=target
        )


        # -----------------------------------------------------
        # Execute the supplied operation.
        # -----------------------------------------------------

        try:

            if operation is None:

                result = {
                    "success": False,
                    "message": (
                        "No execution operation "
                        "was supplied."
                    )
                }

            else:

                result = operation()


        except Exception as error:

            self.logger.action_result(
                action=action,
                target=target,
                result=str(error),
                success=False,
                reason="Executor exception."
            )


            return {

                "success": False,

                "verified": False,

                "message": str(error)
            }


        # -----------------------------------------------------
        # Extract result.
        # -----------------------------------------------------

        if isinstance(
            result,
            tuple
        ):

            success = result[0]
            message = result[1]

        else:

            success = True
            message = result


        # -----------------------------------------------------
        # Don't verify an operation that already failed.
        # -----------------------------------------------------

        if not success:

            self.logger.action_result(
                action=action,
                target=target,
                result=message,
                success=False,
                reason="Action execution failed."
            )


            return {

                "success": False,

                "verified": False,

                "message": message
            }


        # -----------------------------------------------------
        # VERIFY
        # -----------------------------------------------------
        #
        # Three outcomes, not two:
        #   True  - checked, the expected state is present
        #   False - checked, the state is wrong
        #   None  - no verifier exists for this action
        #
        # None must not be reported as a failure. Volume, brightness, Wi-Fi
        # and Bluetooth have no verifier, and treating that as failure made
        # them announce failure after working.
        # -----------------------------------------------------

        verified = self.verifier.verify(

            action=action,

            target=target,

            result=message
        )


        # -----------------------------------------------------
        # EXECUTED, NOT VERIFIABLE
        # -----------------------------------------------------

        if verified is None:

            self.logger.action_executed(
                action=action,
                target=target,
                result=message
            )


            self.logger.action_result(
                action=action,
                target=target,
                result=message,
                success=True,
                reason=(
                    "Action executed. No verifier "
                    "exists for this action."
                )
            )


            return {

                "success": True,

                "verified": None,

                "message": message
            }


        # -----------------------------------------------------
        # VERIFIED SUCCESS
        # -----------------------------------------------------

        if verified:

            self.logger.action_verified(
                action=action,
                target=target,
                result=message
            )


            self.logger.action_result(
                action=action,
                target=target,
                result=message,
                success=True,
                reason="Action executed and verified."
            )


            return {

                "success": True,

                "verified": True,

                "message": message
            }


        # -----------------------------------------------------
        # EXECUTED BUT VERIFICATION FAILED
        # -----------------------------------------------------

        self.logger.action_verification_failed(
            action=action,
            target=target,
            result=message
        )


        self.logger.action_result(
            action=action,
            target=target,
            result=message,
            success=False,
            reason=(
                "Action executed but "
                "verification failed."
            )
        )


        return {

            "success": False,

            "verified": False,

            "message": (
                "The action may have executed, "
                "but Wrecz could not verify "
                "the expected result."
            )
        }