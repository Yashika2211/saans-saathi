"""Build a day plan for one school and print it.

    python -m saans.plan --school demo-1 --replay 2024-11-18
    python -m saans.plan --school demo-2            # today's live forecast
    python -m saans.plan --school demo-1 --replay 2024-11-18 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .aqi import AQI_LABEL
from .forecast import ForecastError, get_hourly
from .planner import DayPlan, plan_day
from .rules import load_rules
from .schools import UnknownSchool, get_school

IST = ZoneInfo("Asia/Kolkata")


def today_ist() -> date:
    return datetime.now(IST).date()


def build_plan(school_key: str, replay: str | date | None = None, offline: bool = False) -> DayPlan:
    """Forecast + timetable + rules -> plan. replay is a past date (YYYY-MM-DD) or None for today."""
    school = get_school(school_key)
    if isinstance(replay, str):
        replay = date.fromisoformat(replay)
    day = replay or today_ist()
    readings = get_hourly(school.lat, school.lon, day, replay=replay is not None, offline=offline)
    return plan_day(school, readings, load_rules(), day, mode="replay" if replay else "live")


ACTION_TAGS = {"keep": "KEEP   ", "indoors": "INDOORS", "reschedule": "MOVE   "}


def render_text(plan: DayPlan) -> str:
    day = date.fromisoformat(plan.date)
    mode = "replay of a past day" if plan.mode == "replay" else "live forecast"
    lines = [
        f"SaansSaathi plan: {plan.school_name}",
        f"{day:%a %d %b %Y} ({mode}), school hours {plan.day_start}–{plan.day_end}",
        "",
        f"{AQI_LABEL} by school hour (hourly PM2.5/PM10, CPCB NAQI breakpoints)",
    ]
    for h in plan.hours:
        if h.aqi is None:
            lines.append(f"  {h.time:>5}    -  no data")
            continue
        mark = "  <- cleanest" if plan.cleanest and h.hour == plan.cleanest.hour else ""
        bar = "#" * max(1, round(h.aqi / 20))
        lines.append(f"  {h.time:>5}  {h.aqi:>3}  {h.category:<12} {bar}{mark}")

    lines += ["", "Plan"]
    for b in plan.blocks:
        lines.append(f"  {ACTION_TAGS[b.action]}  {b.reason}")

    if plan.advisories:
        lines += ["", "Advisories"]
        lines += [f"  - {a}" for a in plan.advisories]

    lines += [
        "",
        f"Impact: {plan.child_hours_protected:g} child-hours of outdoor activity moved out of"
        f" {AQI_LABEL} 201+ air ({plan.blocks_moved} blocks changed)",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m saans.plan", description=__doc__.splitlines()[0])
    parser.add_argument("--school", required=True, help="school id (demo-1) or join code (DEMO1)")
    parser.add_argument("--replay", metavar="YYYY-MM-DD", help="plan a past day from archived forecast data")
    parser.add_argument("--offline", action="store_true", help="use cached data only")
    parser.add_argument("--json", action="store_true", help="print the plan as JSON")
    args = parser.parse_args(argv)

    try:
        plan = build_plan(args.school, args.replay, offline=args.offline)
    except UnknownSchool as exc:
        print(f"Unknown school {exc}", file=sys.stderr)
        return 2
    except ForecastError as exc:
        print(f"Forecast unavailable: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) if args.json else render_text(plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
