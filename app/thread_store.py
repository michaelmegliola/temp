"""In-memory conversation thread store.

A "thread" locks an origination number to a specific endpoint so that
subsequent inbound messages bypass rule-matching and go straight to the
endpoint that replied.  Threads are cleared when the endpoint drops the
conversation, or when the endpoint is deleted.
"""
from __future__ import annotations

# origination_number (E.164) → endpoint_id
_threads: dict[str, str] = {}


def get_thread(number: str) -> str | None:
    return _threads.get(number)


def set_thread(number: str, endpoint_id: str) -> None:
    _threads[number] = endpoint_id


def drop_thread(number: str) -> None:
    _threads.pop(number, None)


def list_threads() -> dict[str, str]:
    return dict(_threads)
