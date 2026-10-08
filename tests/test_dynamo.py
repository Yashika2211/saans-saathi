import boto3
import pytest
from moto import mock_aws

from saans.dynamo import DynamoStore


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="t",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield DynamoStore("t", ddb)


def rec(plan_id, created, status="pending"):
    return {"plan_id": plan_id, "school_id": "demo-1", "created_at": created, "status": status,
            "plan": {"child_hours_protected": 12.5}, "messages": {"parent_hi": "नमस्ते"}}


def test_principal_and_subscribers(store):
    assert store.get_principal("demo-1") is None
    store.set_principal("demo-1", 5)
    assert store.get_principal("demo-1") == 5
    store.add_subscriber("demo-1", 7, "hi")
    store.add_subscriber("demo-1", 8, "en")
    store.add_subscriber("demo-2", 8, "hi")  # moves school
    assert store.subscribers("demo-1") == [(7, "hi")]
    assert store.subscribers("demo-2") == [(8, "hi")]
    assert store.remove_subscriber(7) == "demo-1"
    assert store.remove_subscriber(7) is None


def test_plans_transition_and_latest(store):
    store.save_plan(rec("a", "2026-10-08T00:00:00+00:00"))
    store.save_plan(rec("b", "2026-10-09T00:00:00+00:00"))
    assert store.latest_plan("demo-1")["plan_id"] == "b"
    assert store.get_plan("a")["messages"]["parent_hi"] == "नमस्ते"
    assert store.transition("b", "pending", "approved")
    assert not store.transition("b", "pending", "approved")
    store.update_plan("b", parents_reached=3)
    assert store.get_plan("b")["status"] == "approved"
    assert store.get_plan("b")["parents_reached"] == 3


def test_impact_accumulates(store):
    store.add_impact("demo-1", 12.5, 2)
    store.add_impact("demo-1", 1.5, 1)
    assert store.get_impact("demo-1") == {"child_hours": 14.0, "parents_reached": 3, "plans_sent": 2}
    assert store.get_impact("demo-9")["plans_sent"] == 0
