import os
from dataclasses import dataclass


@dataclass
class TrustResult:
    allowed: bool
    executable: str
    score: int
    reasons: list
    warnings: list
    source: str = ""


class ApplicationTrust:
    """Trust gate for resolved application identities.

    Win32 candidates are validated by executable path.
    Packaged candidates are validated by installed package identity.
    """

    def __init__(self):
        self.trusted_roots = self.get_trusted_roots()

    def get_trusted_roots(self):
        roots = []
        for root in (
            os.environ.get("WINDIR"),
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
        ):
            if root:
                roots.append(os.path.normcase(os.path.abspath(root)))
        return roots

    def verify(self, candidate):
        app_type = str(getattr(candidate, "app_type", "WIN32")).upper()
        source = str(getattr(candidate, "source", ""))

        if app_type == "PACKAGED":
            app_id = str(getattr(candidate, "app_id", "")).strip()
            family = str(getattr(candidate, "package_family", "")).strip().lower()
            if not app_id or "!" not in app_id or not family:
                return TrustResult(False, "", 0, ["Packaged application identity is incomplete."], [], source)
            if app_id.split("!", 1)[0].lower() != family:
                return TrustResult(False, "", 0, ["AppID and package family do not match."], [], source)
            return TrustResult(
                True,
                "",
                95,
                ["AppX/MSIX package identity is verified.", "AppID and package family are consistent."],
                [],
                source,
            )

        executable = os.path.normpath(os.path.abspath(os.path.expandvars(getattr(candidate, "executable", "")))) if getattr(candidate, "executable", "") else ""
        if not executable:
            return TrustResult(False, "", 0, ["No executable path was supplied."], [], source)
        if not executable.lower().endswith(".exe"):
            return TrustResult(False, executable, 0, ["Target is not an .exe file."], [], source)
        if not os.path.isfile(executable):
            return TrustResult(False, executable, 10, ["Executable does not exist."], [], source)
        if os.path.islink(executable):
            return TrustResult(False, executable, 0, ["Executable path is a symbolic link."], [], source)

        try:
            common = os.path.commonpath([os.path.normcase(executable), *self.trusted_roots]) if self.trusted_roots else ""
        except ValueError:
            common = ""
        trusted = any(
            self._under_root(executable, root)
            for root in self.trusted_roots
        )
        score = 90 if trusted else 55
        reasons = ["Executable exists and is a regular file."]
        warnings = []
        if trusted:
            reasons.append("Executable is under a Wrecz trusted application root.")
        else:
            warnings.append("Executable is outside standard trusted roots.")

        return TrustResult(True, executable, score, reasons, warnings, source)

    @staticmethod
    def _under_root(path, root):
        try:
            return os.path.commonpath([os.path.normcase(path), os.path.normcase(root)]) == os.path.normcase(root)
        except ValueError:
            return False