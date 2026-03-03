from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import activity_log, classifier, router, rules_store, service_state, sns_handler
from .models import Rule, RuleCreate, RuleUpdate

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


class _SuppressPolling(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "GET /activity" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(_SuppressPolling())

app = FastAPI(title="SMS Router")

_STATIC = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# Control panel
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def control_panel():
    return HTMLResponse((_STATIC / "index.html").read_text())


@app.get("/monitor", response_class=HTMLResponse, include_in_schema=False)
def monitor():
    return HTMLResponse((_STATIC / "monitor.html").read_text())


# ---------------------------------------------------------------------------
# Service state
# ---------------------------------------------------------------------------

@app.get("/service/status")
def get_service_status():
    return {"enabled": service_state.is_enabled()}


@app.post("/service/start")
def start_service():
    service_state.set_enabled(True)
    activity_log.record("service_started")
    return {"enabled": True}


@app.post("/service/stop")
def stop_service():
    service_state.set_enabled(False)
    activity_log.record("service_stopped")
    return {"enabled": False}


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------

@app.get("/activity")
def get_activity():
    return activity_log.entries()


@app.delete("/activity", status_code=204)
def clear_activity():
    activity_log.clear()


# ---------------------------------------------------------------------------
# Dummy webhooks for testing — use http://localhost:8000/webhooks/<name>
# ---------------------------------------------------------------------------

@app.post("/webhooks/{name}", status_code=200)
def dummy_webhook(name: str, payload: dict):
    logger.info("Dummy webhook [%s] received: %s", name, payload)
    activity_log.record("dummy_webhook", name=name, body=payload.get("body", ""))
    return {"ok": True, "webhook": name}


# ---------------------------------------------------------------------------
# Auto-reply webhook — set DEFAULT_ROUTE_URL=http://localhost:8000/sms/autoreply
# ---------------------------------------------------------------------------

_AUTO_REPLY_MESSAGE = "I will ask around and get back to you"


class _WebhookPayload(BaseModel):
    model_config = {"populate_by_name": True}
    sender: str = Field(alias="from")
    body: str
    message_id: str


@app.post("/sms/autoreply", status_code=200)
def sms_autoreply(payload: _WebhookPayload):
    router.send_sms(payload.sender, _AUTO_REPLY_MESSAGE)
    activity_log.record("auto_reply", to=payload.sender, message=_AUTO_REPLY_MESSAGE)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Inbound SMS webhook (called by AWS SNS)
# ---------------------------------------------------------------------------

@app.post("/sms/inbound", status_code=200)
async def sms_inbound(request: Request):
    if not service_state.is_enabled():
        logger.info("Service stopped — rejecting inbound SMS")
        return Response(status_code=503)

    body = await request.body()
    inbound = await sns_handler.handle_sns_body(body)

    if inbound is None:
        # SubscriptionConfirmation or unrecognised type — already handled
        return Response(status_code=200)

    logger.info("Inbound SMS from %s: %s", inbound.origination_number, inbound.message_body)
    mid = inbound.message_id
    activity_log.record(
        "sms_received",
        message_id=mid,
        sender=inbound.origination_number,
        to=inbound.destination_number,
        body=inbound.message_body,
    )

    rules = rules_store.list_rules()
    try:
        matched_rule = classifier.classify(inbound, rules)
    except Exception as exc:
        logger.warning("Classifier error, falling back to default route: %s", exc)
        activity_log.record("classifier_error", message_id=mid, error=str(exc))
        matched_rule = None

    if matched_rule:
        logger.info("Matched rule '%s' → %s", matched_rule.description, matched_rule.route)
        activity_log.record("rule_matched", message_id=mid, description=matched_rule.description, route=str(matched_rule.route))
        route = matched_rule.route
    else:
        logger.info("No rule matched — using default route")
        default = router.default_route()
        activity_log.record("no_rule_matched", message_id=mid, route=str(default))
        route = default

    try:
        await router.execute_route(route, inbound)
        activity_log.record("route_executed", message_id=mid, detail="success")
    except Exception as exc:
        activity_log.record("route_error", message_id=mid, error=str(exc))
        raise

    return Response(status_code=200)


# ---------------------------------------------------------------------------
# Rules CRUD
# ---------------------------------------------------------------------------

@app.get("/rules", response_model=list[Rule])
def list_rules():
    return rules_store.list_rules()


@app.post("/rules", response_model=Rule, status_code=201)
def create_rule(data: RuleCreate):
    return rules_store.add_rule(data)


@app.put("/rules/{rule_id}", response_model=Rule)
def update_rule(rule_id: str, data: RuleUpdate):
    rule = rules_store.update_rule(rule_id, data)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@app.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: str):
    if not rules_store.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")
