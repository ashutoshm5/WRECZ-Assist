import os
import shutil
from pathlib import Path


class FileManager:

    def __init__(self, workspace=None):

        if workspace is None:
            workspace = os.path.join(
                os.path.dirname(
                    os.path.dirname(__file__)
                ),
                "workspace"
            )

        self.workspace = Path(workspace).resolve()

        self.workspace.mkdir(
            parents=True,
            exist_ok=True
        )


    # =========================================================
    # PATH NORMALIZATION
    # =========================================================

    def normalize_path(self, path):

        if path is None:
            return ""

        path = str(path).strip()

        # Convert Windows backslashes to forward slashes.
        path = path.replace("\\", "/")

        while "//" in path:
            path = path.replace("//", "/")

        return path


    # =========================================================
    # RESOLVE NORMAL PATH
    # =========================================================

    def resolve_path(self, path):

        path = self.normalize_path(path)

        if not path:
            path = "."

        path_obj = Path(path)

        if not path_obj.is_absolute():
            path_obj = self.workspace / path_obj

        try:
            return path_obj.resolve()

        except Exception:
            return None


    # =========================================================
    # CASE-INSENSITIVE PATH RESOLUTION
    # =========================================================

    def resolve_case_insensitive(self, path):

        path = self.normalize_path(path).strip()

        # "." means workspace root.
        if path in ("", "."):
            return self.workspace

        # Remove ./ prefixes.
        while path.startswith("./"):
            path = path[2:]

        path = path.strip("/")

        if not path:
            return self.workspace

        parts = [
            part
            for part in path.split("/")
            if part not in ("", ".")
        ]

        current = self.workspace

        for part in parts:

            if not current.exists():
                return None

            if not current.is_dir():
                return None

            found = None

            try:

                for item in current.iterdir():

                    if item.name.lower() == part.lower():
                        found = item
                        break

            except Exception:
                return None

            if found is None:
                return None

            current = found

        try:
            return current.resolve()

        except Exception:
            return None


    # =========================================================
    # SECURITY
    # =========================================================

    def is_allowed(self, path):

        resolved = self.resolve_path(path)

        if resolved is None:
            return False

        try:

            resolved.relative_to(
                self.workspace
            )

            return True

        except ValueError:

            return False


    # =========================================================
    # RELATIVE DISPLAY PATH
    # =========================================================

    def relative_path(self, path):

        resolved = self.resolve_path(path)

        if resolved is None:
            return None

        try:

            relative = resolved.relative_to(
                self.workspace
            )

            return str(relative).replace(
                "\\",
                "/"
            )

        except ValueError:

            return None


    # =========================================================
    # LIST DIRECTORY
    # =========================================================

    def list_directory(self, path="."):

        if not self.is_allowed(path):

            return (
                False,
                "Access to this path is not allowed."
            )

        resolved = self.resolve_case_insensitive(
            path
        )

        if resolved is None:

            return (
                False,
                "Directory does not exist."
            )

        if not resolved.is_dir():

            return (
                False,
                "The specified path is not a directory."
            )

        items = []

        try:

            for item in sorted(
                resolved.iterdir(),
                key=lambda x: (
                    not x.is_dir(),
                    x.name.lower()
                )
            ):

                items.append({

                    "name": item.name,

                    "path": self.relative_path(
                        item
                    ),

                    "type": (
                        "directory"
                        if item.is_dir()
                        else "file"
                    )
                })

            return (
                True,
                items
            )

        except Exception as error:

            return (
                False,
                f"Could not list directory: {error}"
            )


    # =========================================================
    # SEARCH FILES
    # =========================================================

    def search_files(
        self,
        query,
        path="."
    ):

        if not self.is_allowed(path):

            return (
                False,
                "Access to this path is not allowed."
            )

        resolved = self.resolve_case_insensitive(
            path
        )

        if resolved is None:

            return (
                False,
                "Search directory does not exist."
            )

        if not resolved.is_dir():

            return (
                False,
                "Search path is not a directory."
            )

        query = self.normalize_path(
            query
        ).strip().lower()

        if not query:

            return (
                False,
                "Search query cannot be empty."
            )

        results = []

        try:

            for item in resolved.rglob("*"):

                if query in item.name.lower():

                    results.append({

                        "name": item.name,

                        "path": self.relative_path(
                            item
                        ),

                        "type": (
                            "directory"
                            if item.is_dir()
                            else "file"
                        )
                    })

            return (
                True,
                results
            )

        except Exception as error:

            return (
                False,
                f"File search failed: {error}"
            )


    # =========================================================
    # FIND FILE
    # =========================================================

    def find_file(self, filename):

        filename = self.normalize_path(
            filename
        ).strip()

        if not filename:
            return None

        # First try the complete path.
        resolved = self.resolve_case_insensitive(
            filename
        )

        if (
            resolved is not None
            and resolved.exists()
            and resolved.is_file()
        ):

            return resolved

        # Otherwise search by filename.
        requested_name = Path(
            filename
        ).name.lower()

        matches = []

        try:

            for item in self.workspace.rglob("*"):

                if not item.is_file():
                    continue

                if item.name.lower() == requested_name:

                    matches.append(item)

        except Exception:

            return None

        # Only use automatic resolution if exactly
        # one matching file exists.

        if len(matches) == 1:
            return matches[0]

        return None


    # =========================================================
    # CREATE DIRECTORY
    # =========================================================

    def create_directory(self, name):

        if not self.is_allowed(name):

            return (
                False,
                "Creating outside the Wrecz workspace is blocked."
            )

        path = self.resolve_path(name)

        if path is None:

            return (
                False,
                "Invalid folder path."
            )

        if path.exists():

            return (
                False,
                "A file or folder with that name already exists."
            )

        try:

            path.mkdir(
                parents=True,
                exist_ok=False
            )

            return (
                True,
                f"Created folder: {self.relative_path(path)}"
            )

        except Exception as error:

            return (
                False,
                f"Could not create folder: {error}"
            )


    # =========================================================
    # CREATE FILE
    # =========================================================

    def create_file(
        self,
        name,
        content=""
    ):

        if not self.is_allowed(name):

            return (
                False,
                "Creating outside the Wrecz workspace is blocked."
            )

        path = self.resolve_path(name)

        if path is None:

            return (
                False,
                "Invalid file path."
            )

        if path.exists():

            return (
                False,
                "A file or folder with that name already exists."
            )

        try:

            path.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            path.write_text(
                content,
                encoding="utf-8"
            )

            return (
                True,
                f"Created file: {self.relative_path(path)}"
            )

        except Exception as error:

            return (
                False,
                f"Could not create file: {error}"
            )


    # =========================================================
    # RENAME
    # =========================================================

    def rename(
        self,
        source,
        destination
    ):

        source = self.normalize_path(
            source
        )

        destination = self.normalize_path(
            destination
        )

        if not source:

            return (
                False,
                "Source path is empty."
            )

        if not destination:

            return (
                False,
                "Destination path is empty."
            )

        # Resolve source case-insensitively.
        source_path = self.resolve_case_insensitive(
            source
        )

        # If not found, search for unique filename.
        if (
            source_path is None
            or not source_path.exists()
        ):

            source_path = self.find_file(
                source
            )

        if source_path is None:

            return (
                False,
                f"Source does not exist: {source}"
            )

        if not self.is_allowed(
            source_path
        ):

            return (
                False,
                "Source is outside the Wrecz workspace."
            )

        # Destination doesn't need to exist.
        destination_path = self.resolve_path(
            destination
        )

        if destination_path is None:

            return (
                False,
                "Invalid destination path."
            )

        if destination_path.exists():

            return (
                False,
                "Destination already exists."
            )

        if not self.is_allowed(
            destination_path
        ):

            return (
                False,
                "Destination is outside the Wrecz workspace."
            )

        try:

            destination_path.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            old_name = source_path.name
            new_name = destination_path.name

            source_path.rename(
                destination_path
            )

            return (
                True,
                f"Renamed '{old_name}' to '{new_name}'."
            )

        except Exception as error:

            return (
                False,
                f"Rename failed: {error}"
            )


    # =========================================================
    # MOVE
    # =========================================================

    def move(
        self,
        source,
        destination
    ):

        source = self.normalize_path(
            source
        )

        destination = self.normalize_path(
            destination
        )

        if not source:

            return (
                False,
                "Source path is empty."
            )

        if not destination:

            return (
                False,
                "Destination path is empty."
            )

        source_path = self.resolve_case_insensitive(
            source
        )

        if (
            source_path is None
            or not source_path.exists()
        ):

            source_path = self.find_file(
                source
            )

        if source_path is None:

            return (
                False,
                f"Source does not exist: {source}"
            )

        if not self.is_allowed(
            source_path
        ):

            return (
                False,
                "Source is outside the Wrecz workspace."
            )

        destination_path = self.resolve_case_insensitive(
            destination
        )

        if destination_path is None:

            destination_path = self.resolve_path(
                destination
            )

        if destination_path is None:

            return (
                False,
                "Invalid destination path."
            )

        # Existing directory = move INTO it.
        if destination_path.exists():

            if destination_path.is_dir():

                destination_path = (
                    destination_path /
                    source_path.name
                )

            else:

                return (
                    False,
                    "Destination already exists."
                )

        if not self.is_allowed(
            destination_path
        ):

            return (
                False,
                "Destination is outside the Wrecz workspace."
            )

        if destination_path.exists():

            return (
                False,
                "A file already exists at the destination."
            )

        try:

            destination_path.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            shutil.move(
                str(source_path),
                str(destination_path)
            )

            return (
                True,
                f"Moved '{source_path.name}'."
            )

        except Exception as error:

            return (
                False,
                f"Move failed: {error}"
            )


    # =========================================================
    # DELETE
    # =========================================================

    def delete(self, path):

        path = self.normalize_path(
            path
        )

        if not path:

            return (
                False,
                "Delete path is empty."
            )

        resolved = self.resolve_case_insensitive(
            path
        )

        if (
            resolved is None
            or not resolved.exists()
        ):

            resolved = self.find_file(
                path
            )

        if resolved is None:

            return (
                False,
                f"Path does not exist: {path}"
            )

        if not self.is_allowed(
            resolved
        ):

            return (
                False,
                "Deletion outside the Wrecz workspace is blocked."
            )

        # Never delete workspace itself.
        if resolved == self.workspace:

            return (
                False,
                "Deleting the Wrecz workspace itself is blocked."
            )

        try:

            name = resolved.name

            if resolved.is_dir():

                shutil.rmtree(
                    resolved
                )

            else:

                resolved.unlink()

            return (
                True,
                f"Deleted '{name}'."
            )

        except Exception as error:

            return (
                False,
                f"Delete failed: {error}"
            )