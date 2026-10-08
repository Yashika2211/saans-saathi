"""AWS Lambda entry points.

api_handler     HTTP API: Telegram webhook, /run-now, /status. Returns fast; slow work is
                handed to the worker with an async (Event) invoke.
worker_handler  The slow part: plan + agent + principal message, or voice + parent fan-out.
                Also the target of the 05:30 IST EventBridge schedule.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import date
from functools import lru_cache

import boto3

from .bot import Bot
from .channel import TelegramChannel
from .pipeline import fan_out, run_morning
from .schools import UnknownSchool, get_school, load_schools
from .store import default_store

log = logging.getLogger()
log.setLevel(logging.INFO)


@lru_cache(maxsize=1)
def bot_token() -> str:
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        return os.environ["TELEGRAM_BOT_TOKEN"]
    ssm = boto3.client("ssm")
    return ssm.get_parameter(Name=os.environ["TELEGRAM_TOKEN_PARAM"], WithDecryption=True)["Parameter"]["Value"]


def webhook_secret(token: str) -> str:
    """Telegram echoes this in X-Telegram-Bot-Api-Secret-Token; derived so there is no second secret to manage."""
    return hashlib.sha256(f"saans-webhook:{token}".encode()).hexdigest()[:48]


def invoke_worker(payload: dict) -> None:
    boto3.client("lambda").invoke(
        FunctionName=os.environ["WORKER_FUNCTION"],
        InvocationType="Event",
        Payload=json.dumps(payload).encode(),
    )


def _channel():
    try:
        return TelegramChannel(bot_token())
    except Exception:
        log.exception("Telegram not configured")
        return None


def _response(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body, ensure_ascii=False)}


def _body(event) -> dict:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    return json.loads(raw)


# API

def _telegram(event):
    token = bot_token()
    got = (event.get("headers") or {}).get("x-telegram-bot-api-secret-token", "")
    if not hmac.compare_digest(got, webhook_secret(token)):
        return _response(401, {"error": "bad secret"})

    def dispatch(action, **kw):
        invoke_worker({"action": action, **kw})

    Bot(default_store(), TelegramChannel(token), dispatch).handle(_body(event))
    return _response(200, {"ok": True})  # always 200 so Telegram doesn't retry


def _run_now(event):
    q = event.get("queryStringParameters") or {}
    try:
        school = get_school(q.get("school", ""))
    except UnknownSchool:
        return _response(404, {"error": "unknown school"})
    replay = q.get("replay")
    if replay:
        try:
            date.fromisoformat(replay)
        except ValueError:
            return _response(400, {"error": "replay must be YYYY-MM-DD"})
    invoke_worker({"action": "run", "school_id": school.id, "replay": replay})
    return _response(202, {"queued": True, "school": school.id, "replay": replay})


def _status(event):
    q = event.get("queryStringParameters") or {}
    try:
        school = get_school(q.get("school", "demo-1"))
    except UnknownSchool:
        return _response(404, {"error": "unknown school"})
    store = default_store()
    latest = store.latest_plan(school.id)
    subs = store.subscribers(school.id)
    return _response(200, {
        "school": {"id": school.id, "name": school.name, "area": school.area, "join_code": school.join_code,
                   "students": school.students},
        "principal_registered": store.get_principal(school.id) is not None,
        "subscribers": {"total": len(subs), "hi": sum(1 for _, l in subs if l == "hi"),
                        "en": sum(1 for _, l in subs if l == "en")},
        "impact": store.get_impact(school.id),
        "latest": latest and {k: latest.get(k) for k in
                              ("plan_id", "date", "mode", "status", "created_at", "sent_at", "parents_reached", "plan", "messages")},
    })


def _schools(event):
    return _response(200, {"schools": [{"id": s.id, "name": s.name, "area": s.area, "join_code": s.join_code}
                                       for s in load_schools().values()]})


ROUTES = {
    "POST /telegram": _telegram,
    "POST /run-now": _run_now,
    "GET /status": _status,
    "GET /schools": _schools,
}


def api_handler(event, context):
    route = ROUTES.get(event.get("routeKey", ""))
    if not route:
        return _response(404, {"error": "not found"})
    try:
        return route(event)
    except Exception:
        log.exception("api error on %s", event.get("routeKey"))
        if event.get("routeKey") == "POST /telegram":
            return _response(200, {"ok": False})
        return _response(500, {"error": "internal error"})


# Worker

def worker_handler(event, context):
    action = event.get("action")
    store, channel = default_store(), _channel()
    if action == "run":
        rec = run_morning(event["school_id"], event.get("replay"), store=store, channel=channel)
        return {"plan_id": rec["plan_id"], "messages": rec["messages"]["source"]}
    if action == "run_all":
        out = []
        for school_id in load_schools():
            try:
                rec = run_morning(school_id, None, store=store, channel=channel)
                out.append(rec["plan_id"])
            except Exception:
                log.exception("morning run failed for %s", school_id)
        return {"plans": out}
    if action == "fanout":
        rec = fan_out(event["plan_id"], store=store, channel=channel)
        return {"plan_id": event["plan_id"], "parents_reached": rec.get("parents_reached")}
    raise ValueError(f"unknown action {action!r}")
