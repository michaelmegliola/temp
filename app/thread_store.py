"""Persistent conversation thread store.

A "thread" locks an origination number to a specific endpoint so that
subsequent inbound messages bypass rule-matching and go straight to the
endpoint that replied.  Threads are cleared when the endpoint drops the
conversation, or when the endpoint is deleted.
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import settings


def _path() -> Path:
    p = Path(settings.threads_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load() -> dict[str, str]:
    p = _path()
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def _save(threads: dict[str, str]) -> None:
    _path().write_text(json.dumps(threads, indent=2))


def get_thread(number: str) -> str | None:
    return _load().get(number)


def set_thread(number: str, endpoint_id: str) -> None:
    threads = _load()
    threads[number] = endpoint_id
    _save(threads)


def drop_thread(number: str) -> None:
    threads = _load()
    if number in threads:
        del threads[number]
        _save(threads)


def list_threads() -> dict[str, str]:
    return _load()
