import json

import pytest

from saans import lambdas
from saans.store import JsonStore


@pytest.fixture
def env(tmp_path, monkeypatch):
    store = JsonStore(tmp_path / "s.json")
    invoked = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    lambdas.bot_token.cache_clear()
    monkeypatch.setattr(lambdas, "default_store", lambda: store)
    monkeypatch.setattr(lambdas, "invoke_worker", invoked.append)
    return store, invoked


def call(route, query=None, body=None, headers=None):
    return lambdas.api_handler({"routeKey": route, "queryStringParameters": query, "headers": headers or {},
                                "body": json.dumps(body) if body else None}, None)


def test_run_now_queues_worker(env):
    _, invoked = env
    r = call("POST /run-now", {"school": "demo-1", "replay": "2024-11-18"})
    assert r["statusCode"] == 202
    assert invoked == [{"action": "run", "school_id": "demo-1", "replay": "2024-11-18"}]


def test_run_now_validates(env):
    assert call("POST /run-now", {"school": "nope"})["statusCode"] == 404
    assert call("POST /run-now", {"school": "demo-1", "replay": "18-11-2024"})["statusCode"] == 400


def test_webhook_rejects_wrong_secret(env):
    r = call("POST /telegram", body={"update_id": 1}, headers={"x-telegram-bot-api-secret-token": "nope"})
    assert r["statusCode"] == 401


def test_webhook_handles_update_with_secret(env, monkeypatch):
    store, _ = env
    sent = []
    monkeypatch.setattr(lambdas.TelegramChannel, "send_text", lambda self, c, t, b=None: sent.append((c, t)) or 1)
    secret = lambdas.webhook_secret("123:abc")
    r = call("POST /telegram", body={"update_id": 1, "message": {"chat": {"id": 42}, "text": "/principal DEMO1"}},
             headers={"x-telegram-bot-api-secret-token": secret})
    assert r["statusCode"] == 200
    assert store.get_principal("demo-1") == 42
    assert sent and sent[0][0] == 42


def test_status_shape(env):
    store, _ = env
    store.add_impact("demo-1", 10, 2)
    body = json.loads(call("GET /status", {"school": "demo-1"})["body"])
    assert body["school"]["join_code"] == "DEMO1"
    assert body["impact"]["parents_reached"] == 2
    assert body["latest"] is None


def test_unknown_route(env):
    assert call("GET /nope")["statusCode"] == 404
