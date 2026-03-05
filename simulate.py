#!/usr/bin/env python3
"""CLI tool for simulating inbound SMS and managing routing rules.

Simulate an SMS (bypasses HTTP, hits classifier directly):
    python simulate.py send "Your message here"
    python simulate.py send "Urgent alert" --from +15550001111 --to +15559999999
    python simulate.py send "Urgent alert" --execute

Send via the running server (full SNS pipeline):
    python simulate.py http "Your message here"
    python simulate.py http "Urgent alert" --from +15550001111 --url http://localhost:8000

Manage rules:
    python simulate.py rules list
    python simulate.py rules add "route billing questions to finance" --webhook https://example.com/finance
    python simulate.py rules add "forward alerts to on-call" --sms +15550001111
    python simulate.py rules delete <id>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid

import httpx

# Allow running from the project root without installing the package.
sys.path.insert(0, __file__.rsplit("/", 1)[0])

from app import classifier, router, rules_store
from app.models import InboundSMS, RuleCreate


def _build_inbound(message: str, from_number: str, to_number: str) -> InboundSMS:
    return InboundSMS(
        origination_number=from_number,
        destination_number=to_number,
        message_body=message,
        message_id=str(uuid.uuid4()),
    )


# ---------------------------------------------------------------------------
# rules subcommands
# ---------------------------------------------------------------------------

def cmd_rules_list() -> None:
    from app import endpoints_store
    rules = rules_store.list_rules()
    if not rules:
        print("No rules defined.")
        return
    for rule in rules:
        ep = endpoints_store.get_endpoint(rule.endpoint_id)
        ep_label = f"{ep.name} → {ep.route}" if ep else f"(missing endpoint {rule.endpoint_id})"
        print(f"{rule.id}  {ep_label}  \"{rule.description}\"")


def cmd_rules_add(description: str, route_args: argparse.Namespace) -> None:
    from app import endpoints_store
    from app.models import EndpointCreate
    if route_args.webhook:
        ep_data = EndpointCreate(name=description[:40], type="webhook")
    else:
        ep_data = EndpointCreate(name=description[:40], type="sms", to=route_args.sms)
    ep = endpoints_store.add_endpoint(ep_data)
    rule = rules_store.add_rule(RuleCreate(description=description, endpoint_id=ep.id))
    print(f"Created endpoint: {ep.id}  {ep.route}")
    print(f"Created rule    : {rule.id}  \"{rule.description}\"")


def cmd_rules_delete(rule_id: str) -> None:
    if rules_store.delete_rule(rule_id):
        print(f"Deleted {rule_id}")
    else:
        print(f"No rule found with id {rule_id}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# http subcommand — POSTs SNS-wrapped payload to the running server
# ---------------------------------------------------------------------------

def cmd_http(args: argparse.Namespace) -> None:
    message_id = str(uuid.uuid4())
    inner = json.dumps({
        "originationNumber": args.from_number,
        "destinationNumber": args.to_number,
        "messageBody": args.message,
        "inboundMessageId": message_id,
    })
    envelope = {"Type": "Notification", "MessageId": message_id, "Message": inner}

    print(f"POST {args.url}/sms/inbound")
    print(f"From : {args.from_number}")
    print(f"To   : {args.to_number}")
    print(f'Body : "{args.message}"')
    print()

    response = httpx.post(f"{args.url}/sms/inbound", json=envelope, timeout=60)
    print(f"Response: {response.status_code}")
    if response.text:
        print(response.text)


# ---------------------------------------------------------------------------
# send subcommand
# ---------------------------------------------------------------------------

async def cmd_send(args: argparse.Namespace) -> None:
    from app import endpoints_store, thread_store
    inbound = _build_inbound(args.message, args.from_number, args.to_number)

    print(f"From : {inbound.origination_number}")
    print(f"To   : {inbound.destination_number}")
    print(f'Body : "{inbound.message_body}"')
    print()

    routed_endpoint_id: str | None = None

    active_ep_id = thread_store.get_thread(inbound.origination_number)
    if active_ep_id:
        endpoint = endpoints_store.get_endpoint(active_ep_id)
        if endpoint:
            print(f"Thread active → Endpoint: {endpoint.name} → {endpoint.route}")
            matched_route = endpoint.route
            routed_endpoint_id = endpoint.id
        else:
            thread_store.drop_thread(inbound.origination_number)
            active_ep_id = None

    if not active_ep_id:
        rules = rules_store.list_rules()
        print(f"Loaded {len(rules)} rule(s).")
        matched = classifier.classify(inbound, rules)

        if matched:
            endpoint = endpoints_store.get_endpoint(matched.endpoint_id)
            print(f"Matched rule : {matched.id}")
            print(f'Description  : "{matched.description}"')
            if endpoint:
                print(f"Endpoint     : {endpoint.name} → {endpoint.route}")
                matched_route = endpoint.route
                routed_endpoint_id = endpoint.id
            else:
                print(f"Endpoint     : (missing: {matched.endpoint_id})")
                matched_route = router.default_route()
        else:
            rts = endpoints_store.get_or_create_return_to_sender()
            print("No rule matched — routing to Return to Sender.")
            print(f"Route: {rts.route}")
            matched_route = rts.route

    print()
    if args.execute:
        print("Executing route...")
        await router.execute_route(matched_route, inbound)
        if routed_endpoint_id:
            thread_store.set_thread(inbound.origination_number, routed_endpoint_id)
        print("Done.")
    else:
        print("Dry run — pass --execute to actually fire the route.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(description="SMS router CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    # http
    p_http = sub.add_parser("http", help="POST a simulated SMS to the running server.")
    p_http.add_argument("message", help="The SMS message body")
    p_http.add_argument("--from", dest="from_number", default="+15550000001", metavar="NUMBER")
    p_http.add_argument("--to", dest="to_number", default="+15550000000", metavar="NUMBER")
    p_http.add_argument("--url", default="http://localhost:8000", metavar="URL",
                        help="Base URL of the server (default: http://localhost:8000)")

    # send
    p_send = sub.add_parser("send", help="Simulate an inbound SMS.")
    p_send.add_argument("message", help="The SMS message body")
    p_send.add_argument("--from", dest="from_number", default="+15550000001", metavar="NUMBER")
    p_send.add_argument("--to", dest="to_number", default="+15550000000", metavar="NUMBER")
    p_send.add_argument("--execute", action="store_true",
                        help="Actually fire the route instead of dry-running.")

    # rules
    p_rules = sub.add_parser("rules", help="Manage routing rules.")
    rules_sub = p_rules.add_subparsers(dest="rules_command", required=True)

    rules_sub.add_parser("list", help="List all rules.")

    p_add = rules_sub.add_parser("add", help="Add a new rule.")
    p_add.add_argument("description", help="Plain-English description of when to apply this rule.")
    route_group = p_add.add_mutually_exclusive_group(required=True)
    route_group.add_argument("--webhook", metavar="URL", help="Route to this webhook URL.")
    route_group.add_argument("--sms", metavar="NUMBER", help="Forward to this phone number.")

    p_del = rules_sub.add_parser("delete", help="Delete a rule by ID.")
    p_del.add_argument("id", help="Rule ID to delete.")

    args = parser.parse_args()

    if args.command == "http":
        cmd_http(args)
    elif args.command == "send":
        await cmd_send(args)
    elif args.command == "rules":
        if args.rules_command == "list":
            cmd_rules_list()
        elif args.rules_command == "add":
            cmd_rules_add(args.description, args)
        elif args.rules_command == "delete":
            cmd_rules_delete(args.id)


if __name__ == "__main__":
    asyncio.run(main())
