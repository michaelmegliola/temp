from __future__ import annotations

_enabled: bool = True


def is_enabled() -> bool:
    return _enabled


def set_enabled(value: bool) -> None:
    global _enabled
    _enabled = value
