"""Use Claude to match an inbound SMS against plain-English routing rules."""

from __future__ import annotations

import json
import logging

import anthropic

from .config import settings
from .models import InboundSMS, Rule

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

_TOOL = {
    "name": "route_decision",
    "description": "Report which rule ID matches the message, or null if none match.",
    "input_schema": {
        "type": "object",
        "properties": {
            "matched_rule_id": {
                "type": ["string", "null"],
                "description": "The id of the matching rule, or null if no rule matches.",
            }
        },
        "required": ["matched_rule_id"],
    },
}


def classify(inbound: InboundSMS, rules: list[Rule]) -> Rule | None:
    """Return the first Rule that matches the message, or None."""
    if not rules:
        return None

    rules_text = "\n".join(
        f'- id={r.id}: "{r.description}"' for r in rules
    )

    prompt = (
        f"You are a message router. Below is a list of routing rules, each with an ID and a plain-English description:\n\n"
        f"{rules_text}\n\n"
        f'Incoming message: "{inbound.message_body}"\n\n'
        f"Which rule (if any) best matches this message? "
        f"Call route_decision with the matched rule id, or null if none apply."
    )

    response = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        tools=[_TOOL],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "route_decision":
            matched_id = block.input.get("matched_rule_id")
            if matched_id:
                rule = next((r for r in rules if r.id == matched_id), None)
                if rule:
                    return rule
                logger.warning("Claude returned unknown rule id: %s", matched_id)
            return None

    return None
