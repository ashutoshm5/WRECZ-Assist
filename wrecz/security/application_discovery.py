import json
import os
import re
import subprocess
import winreg
from dataclasses import dataclass


@dataclass
class ApplicationCandidate:
    name: str
    executable: str = ""
    source: str = ""
    registry_path: str = ""
    app_type: str = "WIN32"
    app_id: str = ""
    package_family: str = ""
    install_location: str = ""
    exists: bool = False
    is_file: bool = False
    extension_valid: bool = False
    trusted_location: bool = False
    score: int = 0
    reason: str = ""


class ApplicationDiscovery:
    """Read-only Windows application identity resolver.

    Discovery sources:
      1. HKCU/HKLM App Paths (traditional installers)
      2. PATH (CLI/portable apps exposed on PATH)
      3. Start Menu shortcuts / AppsFolder metadata
      4. Windows packaged AppX/MSIX applications via PowerShell

    It never launches an application and never modifies the system.
    """

    HKCU_APP_PATHS = r"Software\Microsoft\Windows\CurrentVersion\App Paths"
    HKLM_APP_PATHS = r"Software\Microsoft\Windows\CurrentVersion\App Paths"

    def discover(self, application_name):
        name = self.normalize_name(application_name)
        if not name:
            return []

        candidates = []
        candidates.extend(self.search_registry(name))
        candidates.extend(self.search_path(name))
        candidates.extend(self.search_start_apps(name))
        candidates.extend(self.search_start_menu_shortcuts(name))

        candidates = self.remove_duplicates(candidates)
        for candidate in candidates:
            self.validate_candidate(candidate)

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates

    def normalize_name(self, name):
        if name is None:
            return ""
        name = str(name).strip().lower()
        if name.endswith(".exe"):
            name = name[:-4]
        return re.sub(r"\s+", " ", name)

    # ---------------------------------------------------------
    # Traditional Win32 discovery
    # ---------------------------------------------------------
    def search_registry(self, application_name):
        names = {application_name, application_name + ".exe"}
        result = []
        result.extend(self.search_registry_root(winreg.HKEY_CURRENT_USER, self.HKCU_APP_PATHS, names, "HKCU App Paths"))
        result.extend(self.search_registry_root(winreg.HKEY_LOCAL_MACHINE, self.HKLM_APP_PATHS, names, "HKLM App Paths"))
        return result

    def search_registry_root(self, root, registry_path, executable_names, source):
        result = []
        try:
            with winreg.OpenKey(root, registry_path, 0, winreg.KEY_READ) as app_paths:
                count = winreg.QueryInfoKey(app_paths)[0]
                for index in range(count):
                    try:
                        subkey_name = winreg.EnumKey(app_paths, index)
                    except OSError:
                        continue
                    if subkey_name.strip().lower() not in executable_names:
                        continue
                    try:
                        with winreg.OpenKey(app_paths, subkey_name, 0, winreg.KEY_READ) as key:
                            executable = self.read_default_value(key)
                    except OSError:
                        continue
                    if not executable:
                        continue
                    executable = self.clean_executable_path(executable)
                    result.append(ApplicationCandidate(
                        name=self.normalize_name(os.path.splitext(subkey_name)[0]),
                        executable=executable,
                        source=source,
                        registry_path=registry_path + "\\" + subkey_name,
                        app_type="WIN32",
                    ))
        except OSError:
            pass
        return result

    @staticmethod
    def read_default_value(key):
        try:
            value, _ = winreg.QueryValueEx(key, "")
            return value if isinstance(value, str) else None
        except OSError:
            return None

    @staticmethod
    def clean_executable_path(value):
        value = os.path.expandvars(str(value)).strip()
        if value.startswith('"'):
            match = re.match(r'^"([^"]+)"', value)
            if match:
                return match.group(1).strip()
        match = re.search(r"(?i)^(.+?\.exe)", value)
        return match.group(1).strip() if match else value.strip()

    def search_path(self, application_name):
        executable = self.find_on_path(application_name + ".exe")
        if not executable:
            return []
        return [ApplicationCandidate(
            name=application_name,
            executable=executable,
            source="PATH",
            app_type="WIN32",
        )]

    @staticmethod
    def find_on_path(executable_name):
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            directory = directory.strip('" ')
            if not directory:
                continue
            candidate = os.path.join(directory, executable_name)
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)
        return None

    # ---------------------------------------------------------
    # Windows AppsFolder / packaged discovery
    # ---------------------------------------------------------
    def search_start_apps(self, application_name):
        """Resolve Start Apps entries and classify AppX/MSIX entries.

        Get-StartApps is used only as a read-only metadata source.
        """
        rows = self._powershell_json(
            "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
        )
        if not rows:
            return []
        if isinstance(rows, dict):
            rows = [rows]

        packages = self._package_map()
        result = []
        for row in rows:
            display = str(row.get("Name", "")).strip()
            app_id = str(row.get("AppID", "")).strip()
            if not display or not app_id:
                continue
            if not self.name_matches(application_name, display):
                continue

            family = app_id.split("!", 1)[0].lower() if "!" in app_id else ""
            package = packages.get(family)
            if package:
                result.append(ApplicationCandidate(
                    name=self.normalize_name(display),
                    source="START_APPS + APPX/MSIX",
                    app_type="PACKAGED",
                    app_id=app_id,
                    package_family=family,
                    install_location=str(package.get("InstallLocation", "")),
                ))
            else:
                # AUMIDs without a matching package are kept as launcher
                # metadata, but not treated as trusted packaged apps.
                # A corresponding .lnk/EXE candidate can still win.
                if "!" in app_id:
                    result.append(ApplicationCandidate(
                        name=self.normalize_name(display),
                        source="START_APPS",
                        app_type="PACKAGED",
                        app_id=app_id,
                        package_family=family,
                    ))
        return result

    def search_start_menu_shortcuts(self, application_name):
        """Resolve classic .lnk Start Menu entries through WScript.Shell."""
        roots = [
            os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.environ.get("ProgramData", ""), r"Microsoft\Windows\Start Menu\Programs"),
        ]
        shortcuts = []
        for root in roots:
            if not root or not os.path.isdir(root):
                continue
            for current, _, files in os.walk(root):
                for filename in files:
                    if filename.lower().endswith(".lnk"):
                        stem = os.path.splitext(filename)[0]
                        if self.name_matches(application_name, stem):
                            shortcuts.append(os.path.join(current, filename))

        result = []
        for shortcut in shortcuts:
            target = self.resolve_shortcut(shortcut)
            if target and target.lower().endswith(".exe") and os.path.isfile(target):
                result.append(ApplicationCandidate(
                    name=application_name,
                    executable=target,
                    source="START_MENU .LNK",
                    app_type="WIN32",
                ))
        return result

    @staticmethod
    def name_matches(query, display):
        q = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
        d = re.sub(r"[^a-z0-9]+", " ", display.lower()).strip()
        if not q or not d:
            return False
        return q == d or q in d or d in q

    @staticmethod
    def _powershell_json(script):
        try:
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True,
                text=True,
                timeout=12,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode != 0 or not completed.stdout.strip():
                return []
            data = json.loads(completed.stdout)
            return data if isinstance(data, list) else data
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            return []

    def _package_map(self):
        rows = self._powershell_json(
            "Get-AppxPackage | Select-Object Name,PackageFamilyName,InstallLocation | ConvertTo-Json -Compress"
        )
        if not rows:
            return {}
        if isinstance(rows, dict):
            rows = [rows]
        result = {}
        for row in rows:
            family = str(row.get("PackageFamilyName", "")).strip().lower()
            if family:
                result[family] = row
        return result

    @staticmethod
    def resolve_shortcut(path):
        escaped = path.replace("'", "''")
        script = "$s=New-Object -ComObject WScript.Shell; $x=$s.CreateShortcut('" + escaped + "'); $x.TargetPath"
        try:
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            target = completed.stdout.strip()
            return target if completed.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None

    # ---------------------------------------------------------
    # Validation and ranking
    # ---------------------------------------------------------
    def validate_candidate(self, candidate):
        if candidate.app_type == "PACKAGED":
            candidate.exists = bool(candidate.app_id and candidate.package_family)
            candidate.is_file = False
            candidate.extension_valid = True
            candidate.trusted_location = candidate.exists
            candidate.score = 90 if candidate.exists else 0
            candidate.reason = (
                "Installed AppX/MSIX application with verified AppID/package family."
                if candidate.exists
                else "Packaged AppID could not be verified against installed packages."
            )
            return

        executable = os.path.abspath(os.path.expandvars(candidate.executable)) if candidate.executable else ""
        candidate.executable = executable
        candidate.exists = bool(executable and os.path.exists(executable))
        candidate.is_file = bool(candidate.exists and os.path.isfile(executable))
        candidate.extension_valid = bool(candidate.is_file and executable.lower().endswith(".exe"))
        candidate.trusted_location = bool(candidate.extension_valid and self.is_trusted_location(executable))

        if not candidate.extension_valid:
            candidate.score = 0
            candidate.reason = "Executable is missing or is not an .exe file."
            return

        score = 50
        source = candidate.source.lower()
        if "app paths" in source:
            score += 20
        if "start_menu" in source or ".lnk" in source:
            score += 10
        if source == "path":
            score += 5
        if candidate.trusted_location:
            score += 20
        candidate.score = min(score, 100)
        candidate.reason = "Verified executable candidate."

    def is_trusted_location(self, executable):
        executable = os.path.normcase(os.path.abspath(executable))
        roots = [
            os.environ.get("WINDIR", r"C:\Windows"),
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
        ]
        for root in roots:
            if not root:
                continue
            root = os.path.normcase(os.path.abspath(root))
            try:
                if os.path.commonpath([executable, root]) == root:
                    return True
            except ValueError:
                pass
        return False

    @staticmethod
    def remove_duplicates(candidates):
        unique = {}
        for candidate in candidates:
            if candidate.app_type == "PACKAGED":
                key = ("PACKAGED", candidate.app_id.lower())
            else:
                key = ("WIN32", os.path.normcase(os.path.abspath(candidate.executable)) if candidate.executable else "")
            if key not in unique:
                unique[key] = candidate
            else:
                existing = unique[key]
                if candidate.source and candidate.source not in existing.source:
                    existing.source += " + " + candidate.source
        return list(unique.values())


def application_name_from_executable(executable):
    name = str(executable)
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name.lower()