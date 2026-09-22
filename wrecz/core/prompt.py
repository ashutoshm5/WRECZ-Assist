"""Confirmation transport for WRECZ.

WRECZ's security prompts were written for the CLI and call input() directly.
The frontend bridge runs the same Router and SecurityCore inside a server
process where stdin belongs to uvicorn, so a raw input() would block the
request forever.

This module keeps the CLI prompt as the default and lets one caller install a
different confirmation channel for the duration of a single request. Nothing
about the CLI flow in main.py changes: with no provider installed, every
confirmation still reads from the terminal exactly as before.
"""

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field


# =========================================================
# CONFIRMATION REQUEST
# =========================================================

@dataclass(frozen=True)
class ConfirmRequest:
    """One security question that needs a yes/no answer.

    kind is the prompt family, used by a frontend to pick wording:
    "action"   - generic Router confirmation (for example close_app)
    "file"     - filesystem operation covered by SecurityPolicy
    "internet" - internet permission gate
    """

    kind: str
    question: str
    action: str = ""
    target: str = ""
    reason: str = ""
    metadata: dict = field(default_factory=dict)


# =========================================================
# DEFAULT CLI PROVIDER
# =========================================================

def cli_confirm(request):
    """Original WRECZ behaviour: ask on the terminal, default to No."""

    answer = input(
        f"{request.question} [y/N]: "
    ).strip().lower()

    return answer == "y"


# =========================================================
# PROVIDER STORAGE
# =========================================================
#
# The override is thread-local on purpose.
#
# The API bridge runs each request on its own worker thread, so a provider
# installed for one request can never leak into another request or into the
# CLI loop running on the main thread.
#
# =========================================================

_local = threading.local()


def get_confirm_provider():

    return getattr(
        _local,
        "provider",
        None
    ) or cli_confirm


def set_confirm_provider(provider):
    """Install a provider for the current thread. Returns the previous one."""

    previous = getattr(
        _local,
        "provider",
        None
    )

    _local.provider = provider

    return previous


@contextmanager
def confirm_provider(provider):
    """Scope a provider to one block. A provider of None keeps the CLI prompt."""

    previous = set_confirm_provider(provider)

    try:

        yield

    finally:

        set_confirm_provider(previous)


# =========================================================
# ASK
# =========================================================

def ask_confirmation(
    kind,
    question,
    action="",
    target="",
    reason="",
    metadata=None
):
    """Ask the active channel for permission.

    Any failure in the provider is treated as a denial. A confirmation prompt
    that cannot be delivered must never become an implicit yes.
    """

    request = ConfirmRequest(
        kind=kind,
        question=question,
        action=action,
        target=target,
        reason=reason,
        metadata=metadata or {}
    )

    provider = get_confirm_provider()

    try:

        return bool(
            provider(request)
        )

    except Exception as error:

        print(
            "[SECURITY] Confirmation channel failed, "
            f"denying by default: {error}"
        )

        return False
