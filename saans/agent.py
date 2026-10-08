"""Strands agent on Amazon Bedrock that writes the day's messages.

The rule engine has already decided every action. The agent reads the plan through
its tools and only words it: it cannot add, drop or change an action. If Bedrock is
unavailable or the output fails the checks in messages.py, templates are used instead.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date

from pydantic import BaseModel, Field

from .forecast import get_hourly
from .messages import Messages, merge
from .planner import DayPlan
from .schools import get_school

log = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "anthropic.claude-sonnet-5-5"

SYSTEM_PROMPT = """You write the morning air-quality messages for SaansSaathi, a service for schools in Delhi.

A rule engine has already made today's plan. Your job is wording, not deciding:
- Call get_school and compute_plan first. Use get_forecast only if you need the hourly numbers.
- Describe only the actions in the plan (keep, indoors, reschedule). Never add, remove or change an action, time or number.
- Quote AQI values exactly as the plan gives them and call them "AQI (est.)" in English or "AQI अनुमान" in Hindi.
- No medical claims. No blame. Calm, practical tone.

Write three messages:
1. principal_en: for the principal, in English, under 150 words. List every changed block with its reason, the advisories, and the child-hours figure. End by asking them to approve.
2. parent_hi: for parents, in simple everyday Hindi in Devanagari script, under 60 words. What changes for their child today, and what the parent should do (for example a mask). It will also be read aloud as a voice note, so no bullet points, emojis or URLs. Sign off "– साँस साथी".
3. parent_en: the same parent message in plain English, under 60 words, signed "– SaansSaathi".
"""


class DayMessages(BaseModel):
    principal_en: str = Field(description="Summary for the principal, English, under 150 words")
    parent_hi: str = Field(description="Parent message in Hindi (Devanagari), under 60 words")
    parent_en: str = Field(description="Parent message in English, under 60 words")


def _model():
    from strands.models import BedrockModel

    return BedrockModel(
        model_id=os.environ.get("BEDROCK_MODEL_ID") or DEFAULT_MODEL_ID,
        region_name=os.environ.get("BEDROCK_REGION") or os.environ.get("AWS_REGION", "us-east-1"),
        max_tokens=4000,
    )


def _tools(plan: DayPlan):
    """Tools bound to the already-computed plan, so the agent sees exactly what will be approved."""
    from strands import tool

    @tool
    def get_school(school_id: str) -> dict:
        """School name, area, headcount and timetable for a school id such as demo-1."""
        from .schools import get_school as lookup

        s = lookup(school_id)
        return {
            "id": s.id,
            "name": s.name,
            "area": s.area,
            "students": s.students,
            "blocks": [
                {"name": b.name, "start": b.start, "end": b.end, "outdoor": b.outdoor, "students": b.students}
                for b in s.blocks
            ],
        }

    @tool
    def get_forecast(school_id: str) -> list[dict]:
        """Hourly PM2.5, PM10 and AQI (est.) during school hours for today's plan."""
        return [h.__dict__ for h in plan.hours]

    @tool
    def compute_plan(school_id: str) -> dict:
        """Today's rule-based plan: per-block actions with reasons, advisories and impact."""
        if school_id != plan.school_id:
            return {"error": f"Only {plan.school_id} is being planned in this run."}
        d = plan.to_dict()
        d.pop("hours", None)
        return d

    return [get_school, get_forecast, compute_plan]


def write_messages(plan: DayPlan) -> Messages:
    """Agent-written messages, falling back to templates on any failure."""
    if os.environ.get("SAANS_DISABLE_AGENT") == "1":
        return merge(None, plan)
    try:
        from strands import Agent

        agent = Agent(
            model=_model(),
            tools=_tools(plan),
            system_prompt=SYSTEM_PROMPT,
            callback_handler=None,
        )
        mode = "a replay of a past day" if plan.mode == "replay" else "today"
        result = agent(
            f"Prepare the messages for school {plan.school_id} for {plan.date} ({mode}).",
            structured_output_model=DayMessages,
        )
        out = result.structured_output
        if out is None:
            raise RuntimeError("agent returned no structured output")
        messages = merge(out.model_dump(), plan)
        log.info("agent messages: source=%s", messages.source)
        return messages
    except Exception:
        log.exception("agent failed, using templates")
        return merge(None, plan)


if __name__ == "__main__":
    import argparse

    from .plan import build_plan

    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(prog="python -m saans.agent")
    p.add_argument("--school", required=True)
    p.add_argument("--replay", metavar="YYYY-MM-DD")
    args = p.parse_args()
    m = write_messages(build_plan(args.school, args.replay))
    print(json.dumps(m.to_dict(), ensure_ascii=False, indent=2))
