from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any

_log: deque[dict[str, Any]] = deque(maxlen=200)


def record(event: str, **kwargs: Any) -> None:
    _log.appendleft({"ts": datetime.now(timezone.utc).isoformat(), "event": event, **kwargs})


def entries() -> list[dict[str, Any]]:
    return list(_log)


def clear() -> None:
    _log.clear()
