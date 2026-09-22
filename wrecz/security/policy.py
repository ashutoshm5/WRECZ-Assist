class SecurityPolicy:

    SAFE_ACTIONS = {
        "list_files",
        "search_files"
    }

    CONFIRM_ACTIONS = {
        "create_file",
        "create_directory",
        "rename_file",
        "move_file",
        "delete_file"
    }

    BLOCKED_ACTIONS = {
        "system_file_operation",
        "format_drive",
        "modify_registry"
    }


    def classify(
        self,
        action
    ):

        if action in self.SAFE_ACTIONS:

            return "SAFE"

        if action in self.CONFIRM_ACTIONS:

            return "CONFIRM"

        if action in self.BLOCKED_ACTIONS:

            return "BLOCKED"

        return "UNKNOWN"


    def is_path_allowed(
        self,
        file_manager,
        path
    ):

        return file_manager.is_allowed(
            path
        )