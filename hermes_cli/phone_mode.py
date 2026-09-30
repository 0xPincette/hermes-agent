"""Shared parsing and cache-safe behavior for the built-in /phone command."""

from __future__ import annotations

PHONE_MODE_METADATA_KEY = "phone_mode"
_PHONE_DIRECTIVE = (
    "[Phone mode is enabled for this conversation. answer first, keep replies short and scannable, "
    "avoid tables unless explicitly requested, make commands copy-ready, and minimize theory. "
    "preserve security warnings and technical correctness. Do not change tool permissions or approval behavior.]"
)


def parse_phone_command(command: str) -> tuple[str | None, str | None]:
    """Return (action, error) for /phone or its /p alias."""
    parts = (command or "").strip().split()
    if not parts or parts[0].lstrip("/").lower() not in {"phone", "p"}:
        return None, "Usage: /phone [on|off|status]"
    args = parts[1:]
    if not args:
        return "status", None
    if len(args) == 1 and args[0].lower() in {"on", "off", "status"}:
        return args[0].lower(), None
    return None, "Usage: /phone [on|off|status]"


def augment_phone_message(message, enabled: bool):
    """Add the phone directive to one API request without mutating persisted history."""
    if not enabled:
        return message
    if isinstance(message, str):
        return f"{_PHONE_DIRECTIVE}\n\n{message}"
    # Multimodal user messages remain valid OpenAI content parts.
    if isinstance(message, list):
        return [{"type": "text", "text": _PHONE_DIRECTIVE}, *message]
    return message


def format_phone_status(enabled: bool) -> str:
    state = "ON" if enabled else "OFF"
    return f"Phone mode: {state}\nUsage: /phone on|off|status (alias: /p)"
