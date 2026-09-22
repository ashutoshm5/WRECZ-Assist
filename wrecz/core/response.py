"""
Natural response layer for Wrecz.

The action router remains responsible for execution and security.
This module only turns a completed action into a short, human response.
"""

import re


def _failed(result):
    text = str(result or "").lower()
    return any(
        phrase in text
        for phrase in (
            "failed",
            "blocked",
            "denied",
            "cancelled",
            "could not",
            "cannot",
            "error",
            "rejected",
            "not enabled",
        )
    )


def respond(command, execution_result):
    action = command.get("action", "")
    target = str(command.get("target", "")).strip()
    result = str(execution_result or "").strip()

    if _failed(result):
        return result

    if action == "open_app":
        return f"Sure — opening {target}."

    if action == "close_app":
        return f"Done — closed {target}."

    if action == "volume_control":
        if target == "mute":
            return "Done — muted the sound."
        if target == "unmute":
            return "Done — sound is back on."
        if target == "get":
            return result or "Let me check the current volume."
        if target.startswith("increase|"):
            amount = target.split("|", 1)[1]
            return (
                "Done — turned it up a bit."
                if amount == "10"
                else f"Done — increased it by {amount}%."
            )
        if target.startswith("decrease|"):
            amount = target.split("|", 1)[1]
            return (
                "Done — lowered it a bit."
                if amount == "10"
                else f"Done — decreased it by {amount}%."
            )
        if target.startswith("set|"):
            value = target.split("|", 1)[1]
            return f"Done — volume is now at {value}%."

    if action == "brightness_control":
        if target == "get":
            return result or "Let me check the current brightness."
        if target.startswith("increase|"):
            return "Done — made the screen a little brighter."
        if target.startswith("decrease|"):
            return "Done — made the screen a little darker."
        if target.startswith("set|"):
            value = target.split("|", 1)[1]
            return f"Done — brightness is now at {value}%."

    if action == "wifi_control":
        if target == "on":
            return "Done — Wi-Fi is back on."
        if target == "off":
            return "Done — Wi-Fi is off."
        return result or "I checked the Wi-Fi status."

    if action == "bluetooth_control":
        if target == "on":
            return "Done — Bluetooth is back on."
        if target == "off":
            return "Done — Bluetooth is off."
        return result or "I checked the Bluetooth status."

    if action == "web_search":
        return result or "I'm on it."

    if action == "list_files":
        return result or "I couldn't find anything to show."

    if action == "search_files":
        return result or "I couldn't find any matching files."

    if action == "create_file":
        return f"Done — created {target}."

    if action == "create_directory":
        return f"Done — created the {target} folder."

    if action == "rename_file":
        return "Done — renamed it."

    if action == "move_file":
        return "Done — moved it."

    if action == "delete_file":
        return "Done — deleted it."

    if action == "clarification":
        return (
            "I need one more detail before I do that."
        )

    if action == "unsupported":
        return (
            "I understand what you want. I just don't have "
            "that capability connected yet."
        )

    return result or "Done."
