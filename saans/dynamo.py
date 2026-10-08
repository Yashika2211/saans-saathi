"""Single-table DynamoDB store with the same methods as JsonStore.

    pk                  sk                          what
    SCHOOL#<id>         PRINCIPAL                   chat_id of the approver
    SCHOOL#<id>         SUB#<chat_id>               parent subscription (lang)
    CHAT#<chat_id>      SUB                         which school a parent chat belongs to
    PLAN#<plan_id>      PLAN                        plan record: status + JSON data
    SCHOOL#<id>         PLANAT#<created>#<plan_id>  index for "latest plan"
    SCHOOL#<id>         IMPACT                      running totals (atomic ADD)
"""

from __future__ import annotations

import json
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from .store import EMPTY_IMPACT


class DynamoStore:
    def __init__(self, table_name: str, resource=None):
        self.table = (resource or boto3.resource("dynamodb")).Table(table_name)

    def set_principal(self, school_id, chat_id):
        self.table.put_item(Item={"pk": f"SCHOOL#{school_id}", "sk": "PRINCIPAL", "chat_id": int(chat_id)})

    def get_principal(self, school_id):
        item = self.table.get_item(Key={"pk": f"SCHOOL#{school_id}", "sk": "PRINCIPAL"}).get("Item")
        return int(item["chat_id"]) if item else None

    def add_subscriber(self, school_id, chat_id, lang):
        self.remove_subscriber(chat_id)
        self.table.put_item(Item={"pk": f"SCHOOL#{school_id}", "sk": f"SUB#{chat_id}", "chat_id": int(chat_id), "lang": lang})
        self.table.put_item(Item={"pk": f"CHAT#{chat_id}", "sk": "SUB", "school_id": school_id})

    def remove_subscriber(self, chat_id):
        item = self.table.get_item(Key={"pk": f"CHAT#{chat_id}", "sk": "SUB"}).get("Item")
        if not item:
            return None
        self.table.delete_item(Key={"pk": f"SCHOOL#{item['school_id']}", "sk": f"SUB#{chat_id}"})
        self.table.delete_item(Key={"pk": f"CHAT#{chat_id}", "sk": "SUB"})
        return item["school_id"]

    def subscribers(self, school_id):
        out, kwargs = [], {"KeyConditionExpression": Key("pk").eq(f"SCHOOL#{school_id}") & Key("sk").begins_with("SUB#")}
        while True:
            resp = self.table.query(**kwargs)
            out += [(int(i["chat_id"]), i["lang"]) for i in resp["Items"]]
            if "LastEvaluatedKey" not in resp:
                return out
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    # Plans: status is a top-level attribute so approval can be a conditional write.

    def _put_plan(self, rec, condition_status=None):
        data = {k: v for k, v in rec.items() if k != "status"}
        kwargs = {}
        if condition_status:
            kwargs = {"ConditionExpression": "#s = :from", "ExpressionAttributeNames": {"#s": "status"},
                      "ExpressionAttributeValues": {":from": condition_status}}
        self.table.put_item(
            Item={"pk": f"PLAN#{rec['plan_id']}", "sk": "PLAN", "status": rec["status"],
                  "data": json.dumps(data, ensure_ascii=False)},
            **kwargs,
        )

    def save_plan(self, rec):
        self._put_plan(rec)
        self.table.put_item(Item={"pk": f"SCHOOL#{rec['school_id']}", "sk": f"PLANAT#{rec['created_at']}#{rec['plan_id']}",
                                  "plan_id": rec["plan_id"]})

    def get_plan(self, plan_id):
        item = self.table.get_item(Key={"pk": f"PLAN#{plan_id}", "sk": "PLAN"}, ConsistentRead=True).get("Item")
        if not item:
            return None
        return {**json.loads(item["data"]), "status": item["status"]}

    def update_plan(self, plan_id, **fields):
        rec = self.get_plan(plan_id)
        rec.update(fields)
        self._put_plan(rec)

    def transition(self, plan_id, from_status, to_status, **fields):
        rec = self.get_plan(plan_id)
        if not rec or rec["status"] != from_status:
            return False
        rec.update(fields, status=to_status)
        try:
            self._put_plan(rec, condition_status=from_status)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def latest_plan(self, school_id):
        resp = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"SCHOOL#{school_id}") & Key("sk").begins_with("PLANAT#"),
            ScanIndexForward=False,
            Limit=1,
        )
        return self.get_plan(resp["Items"][0]["plan_id"]) if resp["Items"] else None

    def add_impact(self, school_id, child_hours, parents):
        self.table.update_item(
            Key={"pk": f"SCHOOL#{school_id}", "sk": "IMPACT"},
            UpdateExpression="ADD child_hours :c, parents_reached :p, plans_sent :one",
            ExpressionAttributeValues={":c": Decimal(str(child_hours)), ":p": parents, ":one": 1},
        )

    def get_impact(self, school_id):
        item = self.table.get_item(Key={"pk": f"SCHOOL#{school_id}", "sk": "IMPACT"}).get("Item")
        if not item:
            return dict(EMPTY_IMPACT)
        return {"child_hours": float(item["child_hours"]), "parents_reached": int(item["parents_reached"]),
                "plans_sent": int(item["plans_sent"])}
