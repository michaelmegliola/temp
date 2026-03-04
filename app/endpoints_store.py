from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import uuid4

from .config import settings
from .models import Endpoint, EndpointCreate, SmsRoute, WebhookRoute


def _path() -> Path:
    p = Path(settings.endpoints_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load() -> list[Endpoint]:
    p = _path()
    if not p.exists():
        return []
    return [Endpoint.model_validate(e) for e in json.loads(p.read_text())]


def _save(endpoints: list[Endpoint]) -> None:
    _path().write_text(
        json.dumps([e.model_dump(mode="json") for e in endpoints], indent=2)
    )


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "webhook"


def _unique_slug(base: str, existing: set[str]) -> str:
    if base not in existing:
        return base
    return f"{base}_{str(uuid4())[:6]}"


def list_endpoints() -> list[Endpoint]:
    return _load()


def get_endpoint(endpoint_id: str) -> Endpoint | None:
    return next((e for e in _load() if e.id == endpoint_id), None)


def add_endpoint(data: EndpointCreate) -> Endpoint:
    endpoints = _load()
    if data.type == "webhook":
        existing_slugs = {
            e.route.url.rstrip("/").split("/")[-1]
            for e in endpoints
            if e.route.type == "webhook"
        }
        slug = _unique_slug(_slugify(data.name), existing_slugs)
        url = f"{settings.base_url.rstrip('/')}/webhooks/{slug}"
        route: WebhookRoute | SmsRoute = WebhookRoute(type="webhook", url=url)
    else:
        route = SmsRoute(type="sms", to=data.to or "")
    endpoint = Endpoint(name=data.name, route=route)
    endpoints.append(endpoint)
    _save(endpoints)
    return endpoint


def delete_endpoint(endpoint_id: str) -> bool:
    endpoints = _load()
    filtered = [e for e in endpoints if e.id != endpoint_id]
    if len(filtered) == len(endpoints):
        return False
    _save(filtered)
    return True
