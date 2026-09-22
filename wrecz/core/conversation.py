"""
Wrecz conversational state.

Keeps a short rolling memory so commands can refer to previous turns:
"close it", "a bit more", "do that again", "make it quieter", etc.

This state is intentionally in-memory only. It is not a long-term personal-data store.
"""

from __future__ import annotations

import re
from collections import deque


class ConversationState:
    def __init__(self, max_turns: int = 8):
        self.max_turns = max_turns
        self.turns = deque(maxlen=max_turns)

        self.last_application = None
        self.last_file = None
        self.last_command = None

    def resolve(self, text: str) -> str:
        """Resolve lightweight conversational references before classification."""
        text = re.sub(r"\s+", " ", str(text).strip())

        if not text:
            return text

        lower = text.lower()

        # ---------------------------------------------------------
        # APPLICATION REFERENCES
        # ---------------------------------------------------------
        if self.last_application:
            if re.search(
                r"\b(close|exit|quit|shut|terminate)\s+"
                r"(it|that|this|the app|the application)\b",
                lower,
            ):
                return re.sub(
                    r"\b(it|that|this|the app|the application)\b",
                    self.last_application,
                    text,
                    count=1,
                    flags=re.IGNORECASE,
                )

            if re.search(
                r"\b(open|launch|start|run)\s+"
                r"(it|that|this)\b",
                lower,
            ):
                return re.sub(
                    r"\b(it|that|this)\b",
                    self.last_application,
                    text,
                    count=1,
                    flags=re.IGNORECASE,
                )

        # ---------------------------------------------------------
        # RELATIVE VOLUME / BRIGHTNESS CONTINUATION
        # ---------------------------------------------------------
        last = self.last_command or {}
        action = last.get("action", "")
        target = str(last.get("target", "")).lower()

        is_relative = bool(
            re.search(
                r"\b(a bit|a little|little|slightly|somewhat|"
                r"bit|more|less|again|further)\b",
                lower,
            )
        )

        if is_relative and action in {
            "volume_control",
            "brightness_control",
        }:
            domain = (
                "volume"
                if action == "volume_control"
                else "brightness"
            )

            if target.startswith("increase|"):
                direction = "increase"
            elif target.startswith("decrease|"):
                direction = "decrease"
            else:
                direction = None

            # "that's too loud/high" means reverse the last change.
            if re.search(
                r"\b(too loud|too high|too bright|too much|"
                r"less|lower|quieter|darker)\b",
                lower,
            ):
                direction = "decrease"

            if re.search(
                r"\b(too quiet|too low|too dark|"
                r"more|higher|brighter|louder)\b",
                lower,
            ):
                direction = "increase"

            if direction:
                return f"{direction} {domain}"

        return text

    def record(self, user_text: str, command: dict) -> None:
        """Store a compact representation of the completed turn."""
        command = dict(command or {})

        action = command.get("action", "")
        target = command.get("target", "")

        self.last_command = command

        if action == "open_app" and target:
            self.last_application = str(target).strip()

        self.turns.append(
            {
                "user": str(user_text).strip(),
                "action": action,
                "target": str(target),
                "intent": command.get("intent", ""),
            }
        )

    def llm_context(self) -> str:
        """Compact context for the classifier; avoids sending a huge history."""
        if not self.turns:
            return "No previous conversation context."

        lines = []
        for turn in self.turns:
            lines.append(
                f'User: {turn["user"]}\n'
                f'Wrecz action: {turn["action"]} | '
                f'target: {turn["target"]}'
            )

        return "\n\n".join(lines)

    def reset(self) -> None:
        self.turns.clear()
        self.last_application = None
        self.last_file = None
        self.last_command = None


STATE = ConversationState()
