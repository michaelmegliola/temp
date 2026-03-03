"""Parse AWS SNS HTTP notifications and extract Pinpoint inbound SMS payloads."""

from __future__ import annotations

import json
import logging

import httpx

from .models import InboundSMS

logger = logging.getLogger(__name__)


async def handle_sns_body(raw_body: bytes) -> InboundSMS | None:
    """
    Process an SNS HTTP POST body.

    Returns an InboundSMS if this is a Notification containing a Pinpoint
    inbound message, otherwise returns None (e.g. subscription confirmation
    is handled internally and None is returned so the caller can 200 OK).
    """
    try:
        envelope = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.error("SNS body is not valid JSON")
        return None

    msg_type = envelope.get("Type")

    if msg_type == "SubscriptionConfirmation":
        subscribe_url = envelope.get("SubscribeURL")
        if subscribe_url:
            logger.info("Confirming SNS subscription: %s", subscribe_url)
            async with httpx.AsyncClient() as client:
                await client.get(subscribe_url)
        return None

    if msg_type == "Notification":
        try:
            payload = json.loads(envelope["Message"])
        except (KeyError, json.JSONDecodeError):
            logger.error("Could not parse SNS Message field as JSON")
            return None

        # Pinpoint inbound SMS payload keys
        origination = payload.get("originationNumber") or payload.get("originationNumber")
        destination = payload.get("destinationNumber")
        body = payload.get("messageBody", "")
        message_id = payload.get("inboundMessageId", envelope.get("MessageId", ""))

        if not origination or not destination:
            logger.warning("SNS notification missing phone number fields: %s", payload)
            return None

        return InboundSMS(
            origination_number=origination,
            destination_number=destination,
            message_body=body,
            message_id=message_id,
        )

    logger.warning("Unhandled SNS message type: %s", msg_type)
    return None
