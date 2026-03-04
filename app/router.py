"""Execute routing actions: HTTP webhook or SMS forwarding via Pinpoint."""

from __future__ import annotations

import logging

import boto3
import httpx

from .config import settings
from .models import InboundSMS, RouteConfig, SmsRoute, WebhookRoute

logger = logging.getLogger(__name__)


async def execute_route(route: RouteConfig, inbound: InboundSMS) -> None:
    if isinstance(route, WebhookRoute):
        await _send_webhook(route, inbound)
    elif isinstance(route, SmsRoute):
        _send_sms(route, inbound)


async def _send_webhook(route: WebhookRoute, inbound: InboundSMS) -> None:
    payload = {
        "from": inbound.origination_number,
        "to": inbound.destination_number,
        "body": inbound.message_body,
        "message_id": inbound.message_id,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(route.url, json=payload)
        logger.info("Webhook %s responded %s", route.url, response.status_code)
        response.raise_for_status()


def _send_sms(route: SmsRoute, inbound: InboundSMS) -> None:
    send_sms(route.to, inbound.message_body)


def send_sms(to: str, message: str) -> None:
    """Send an SMS via AWS End User Messaging (pinpoint-sms-voice-v2).

    If no origination number is configured the call is logged but skipped
    so the rest of the application keeps working without real AWS credentials.
    """
    if not settings.pinpoint_origination_number:
        logger.info("SMS (dummy — no origination number configured): to=%s body=%r", to, message)
        return
    client = boto3.client(
        "pinpoint-sms-voice-v2",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
    )
    response = client.send_text_message(
        DestinationPhoneNumber=to,
        OriginationIdentity=settings.pinpoint_origination_number,
        MessageBody=message,
        MessageType="TRANSACTIONAL",
    )
    logger.info("SMS to %s: message id %s", to, response.get("MessageId"))


def default_route() -> RouteConfig:
    if settings.default_route_type == "sms":
        return SmsRoute(type="sms", to=settings.default_route_to)
    return WebhookRoute(type="webhook", url=settings.default_route_url)
