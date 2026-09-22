import os
import subprocess

from security.application_discovery import ApplicationDiscovery
from security.application_trust import ApplicationTrust
from security.window_manager import get_window_manager


discovery = ApplicationDiscovery()
trust = ApplicationTrust()
window_manager = get_window_manager()


def normalize_app_name(name):
    return "" if name is None else str(name).strip().lower()


def discover_application(name):
    candidates = discovery.discover(normalize_app_name(name))
    return candidates[0] if candidates else None


def _launch_win32(candidate):
    executable = candidate.executable
    if not executable or not os.path.isfile(executable):
        return False, "The discovered executable no longer exists."
    before = window_manager.snapshot()
    try:
        subprocess.Popen([executable], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    except Exception as error:
        return False, f"Could not open {candidate.name}: {error}"

    # Some apps reuse an existing instance. If no new window appears,
    # the application may still have been activated successfully.
    window = window_manager.find_new_application_window(before, application=candidate.name, executable=executable, timeout=8.0)
    if window:
        window_manager.register_window(candidate.name, window, executable=executable, app_type="WIN32")
        return True, f"Opening {candidate.name}."
    return True, f"Opening {candidate.name}."


def _launch_packaged(candidate):
    if not candidate.app_id or not candidate.package_family:
        return False, f"Packaged identity for {candidate.name} could not be verified."
    before = window_manager.snapshot()
    try:
        subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + candidate.app_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    except Exception as error:
        return False, f"Could not open {candidate.name}: {error}"

    window = window_manager.find_new_application_window(before, application=candidate.name, app_id=candidate.app_id, timeout=10.0)
    if window:
        if not window_manager.register_packaged_window(candidate.name, window, candidate.app_id):
            return False, f"Opened {candidate.name}, but Wrecz could not register its verified window."
        return True, f"Opening {candidate.name}."
    return True, f"Opening {candidate.name}."


def open_app(name):
    candidate = discover_application(name)
    if not candidate:
        return False, f"Could not safely locate the application '{name}'."

    # Second opinion before launching. Discovery decides *which* program a
    # name refers to; trust decides whether that program is safe to run.
    # It is not redundant: this is the only check that rejects a symlinked
    # executable, which could point a trusted-looking path anywhere.
    decision = trust.verify(candidate)

    if not decision.allowed:
        reason = decision.reasons[0] if decision.reasons else "Trust check failed."
        return False, f"Wrecz will not launch '{name}': {reason}"

    for warning in decision.warnings:
        print(f"[TRUST] {candidate.name}: {warning}")

    if candidate.app_type == "PACKAGED":
        return _launch_packaged(candidate)
    return _launch_win32(candidate)


def close_app(name):
    name = normalize_app_name(name)
    # First preference: exact HWND Wrecz already owns.
    success, message = window_manager.close_owned_window(name)
    if success:
        return success, message

    # Second preference: resolve an already-running instance by identity.
    success, message = window_manager.close_existing_window(name)
    return success, message


def list_running_apps():
    try:
        output = subprocess.check_output(["tasklist", "/fo", "csv", "/nh"], text=True, stderr=subprocess.DEVNULL)
        apps = []
        for line in output.splitlines():
            if line.strip():
                apps.append(line.split('","')[0].strip('"'))
        return True, apps
    except Exception as error:
        return False, f"Could not retrieve running applications: {error}"


def is_app_running(name):
    candidate = discover_application(name)
    if not candidate:
        return False
    if window_manager.get_owned_window(name):
        return window_manager.verify_ownership(name)
    window, _ = window_manager.find_existing_window(name)
    return bool(window)