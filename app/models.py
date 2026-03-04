from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class WebhookRoute(BaseModel):
    type: Literal["webhook"]
    url: str


class SmsRoute(BaseModel):
    type: Literal["sms"]
    to: str  # E.164 phone number


RouteConfig = Annotated[WebhookRoute | SmsRoute, Field(discriminator="type")]


class Endpoint(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    route: RouteConfig
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EndpointCreate(BaseModel):
    name: str
    type: Literal["webhook", "sms"]
    to: str | None = None  # only for type=sms


class Rule(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    description: str
    endpoint_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RuleCreate(BaseModel):
    description: str
    endpoint_id: str


class RuleUpdate(BaseModel):
    description: str | None = None
    endpoint_id: str | None = None


class InboundSMS(BaseModel):
    origination_number: str
    destination_number: str
    message_body: str
    message_id: str
