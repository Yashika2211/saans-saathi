"""Persistence for principals, subscribers, plans and impact.

JsonStore is for local runs. DynamoStore (saans/dynamo.py) implements the same methods
on one DynamoDB table in AWS.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Protocol

DATA_DIR = Path(os.environ.get("SAANS_DATA_DIR", Path(__file__).resolve().parent.parent / ".data"))


class Store(Protocol):
    def set_principal(self, school_id: str, chat_id: int) -> None: ...
    def get_principal(self, school_id: str) -> int | None: ...
    def add_subscriber(self, school_id: str, chat_id: int, lang: str) -> None: ...
    def remove_subscriber(self, chat_id: int) -> str | None: ...
    def subscribers(self, school_id: str) -> list[tuple[int, str]]: ...
    def save_plan(self, rec: dict) -> None: ...
    def get_plan(self, plan_id: str) -> dict | None: ...
    def update_plan(self, plan_id: str, **fields) -> None: ...
    def transition(self, plan_id: str, from_status: str, to_status: str, **fields) -> bool: ...
    def latest_plan(self, school_id: str) -> dict | None: ...
    def add_impact(self, school_id: str, child_hours: float, parents: int) -> None: ...
    def get_impact(self, school_id: str) -> dict: ...


EMPTY_IMPACT = {"child_hours": 0.0, "parents_reached": 0, "plans_sent": 0}


class JsonStore:
    def __init__(self, path: Path | None = None):
        self.path = path or DATA_DIR / "store.json"
        self._lock = threading.Lock()

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {"principals": {}, "subscribers": {}, "plans": {}, "impact": {}}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
        tmp.replace(self.path)

    def _edit(self, fn):
        with self._lock:
            data = self._load()
            result = fn(data)
            self._save(data)
            return result

    def set_principal(self, school_id, chat_id):
        self._edit(lambda d: d["principals"].__setitem__(school_id, int(chat_id)))

    def get_principal(self, school_id):
        return self._load()["principals"].get(school_id)

    def add_subscriber(self, school_id, chat_id, lang):
        def fn(d):
            for subs in d["subscribers"].values():
                subs.pop(str(chat_id), None)  # one school per parent chat
            d["subscribers"].setdefault(school_id, {})[str(chat_id)] = lang

        self._edit(fn)

    def remove_subscriber(self, chat_id):
        def fn(d):
            for school_id, subs in d["subscribers"].items():
                if subs.pop(str(chat_id), None):
                    return school_id
            return None

        return self._edit(fn)

    def subscribers(self, school_id):
        subs = self._load()["subscribers"].get(school_id, {})
        return [(int(c), lang) for c, lang in subs.items()]

    def save_plan(self, rec):
        self._edit(lambda d: d["plans"].__setitem__(rec["plan_id"], rec))

    def get_plan(self, plan_id):
        return self._load()["plans"].get(plan_id)

    def update_plan(self, plan_id, **fields):
        self._edit(lambda d: d["plans"][plan_id].update(fields))

    def transition(self, plan_id, from_status, to_status, **fields):
        def fn(d):
            rec = d["plans"].get(plan_id)
            if not rec or rec["status"] != from_status:
                return False
            rec.update(fields, status=to_status)
            return True

        return self._edit(fn)

    def latest_plan(self, school_id):
        plans = [p for p in self._load()["plans"].values() if p["school_id"] == school_id]
        return max(plans, key=lambda p: p["created_at"]) if plans else None

    def add_impact(self, school_id, child_hours, parents):
        def fn(d):
            imp = d["impact"].setdefault(school_id, dict(EMPTY_IMPACT))
            imp["child_hours"] = round(imp["child_hours"] + child_hours, 1)
            imp["parents_reached"] += parents
            imp["plans_sent"] += 1

        self._edit(fn)

    def get_impact(self, school_id):
        return self._load()["impact"].get(school_id, dict(EMPTY_IMPACT))


def default_store() -> Store:
    if os.environ.get("TABLE_NAME"):
        from .dynamo import DynamoStore

        return DynamoStore(os.environ["TABLE_NAME"])
    return JsonStore()
