"""Turn an hourly AQI (est.) forecast and a timetable into a plan for the school day.

The planner is deterministic. It decides every action; the agent later only words it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from .aqi import AQI_LABEL, aqi_est, category
from .forecast import HourReading
from .rules import Rules
from .schools import Block, School, fmt_time


@dataclass
class HourAQI:
    hour: int
    time: str
    pm25: float | None
    pm10: float | None
    aqi: int | None
    category: str | None
    color: str | None


@dataclass
class BlockPlan:
    name: str
    start: str
    end: str
    students: int
    outdoor: bool
    action: str  # keep | indoors | reschedule
    aqi: int | None
    new_start: str | None = None
    new_end: str | None = None
    new_aqi: int | None = None
    reason: str = ""
    child_hours: float = 0.0  # moved out of bad air


@dataclass
class DayPlan:
    school_id: str
    school_name: str
    date: str
    mode: str  # live | replay
    aqi_label: str
    day_start: str
    day_end: str
    hours: list[HourAQI]
    worst: HourAQI | None
    cleanest: HourAQI | None
    day_band: str | None
    blocks: list[BlockPlan]
    windows_closed: list[list[str]]
    advisories: list[str]
    child_hours_protected: float
    blocks_moved: int

    def to_dict(self) -> dict:
        return asdict(self)


def _slots(start: int, end: int) -> range:
    """Clock hours whose [h:00, h+1:00) overlaps [start, end) minutes."""
    return range(start // 60, (end - 1) // 60 + 1)


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


class _Air:
    def __init__(self, readings: list[HourReading]):
        self.by_hour: dict[int, HourAQI] = {}
        for r in readings:
            aqi = aqi_est(r.pm25, r.pm10)
            cat = category(aqi)
            self.by_hour[r.time.hour] = HourAQI(
                hour=r.time.hour,
                time=f"{r.time.hour}:00",
                pm25=None if r.pm25 is None else round(r.pm25, 1),
                pm10=None if r.pm10 is None else round(r.pm10, 1),
                aqi=aqi,
                category=cat.name if cat else None,
                color=cat.color if cat else None,
            )

    def window(self, start: int, end: int) -> int | None:
        values = [self.by_hour[h].aqi for h in _slots(start, end) if h in self.by_hour]
        values = [v for v in values if v is not None]
        return max(values) if values else None

    def hours(self, start: int, end: int) -> list[HourAQI]:
        return [self.by_hour[h] for h in _slots(start, end) if h in self.by_hour]


def _best_window(
    block: Block, school: School, air: _Air, rules: Rules, busy: list[tuple[int, int]]
) -> tuple[int, int] | None:
    """Cleanest free start time (minutes) inside school hours, with its AQI (est.)."""
    duration = block.end - block.start
    # Grid starts, plus right after each busy block so moved periods can sit back to back.
    starts = set(range(school.day_start, school.day_end, rules.step_minutes)) | {b1 for _, b1 in busy}
    best: tuple[int, int, int] | None = None  # (aqi, distance, start)
    for start in sorted(starts):
        end = start + duration
        if start < school.day_start or end > school.day_end:
            continue
        if any(_overlaps(start, end, b0, b1) for b0, b1 in busy):
            continue
        aqi = air.window(start, end)
        if aqi is not None:
            key = (aqi, abs(start - block.start), start)
            if best is None or key < best:
                best = key
    return (best[2], best[0]) if best else None


def _with_note(text: str, rules: Rules, aqi: int | None) -> str:
    if aqi is None:
        return text
    note = rules.band_for(aqi).note
    return f"{text}, {note}" if note else text


def _ranges(hours: list[HourAQI], threshold: int, day_start: int, day_end: int) -> list[list[str]]:
    ranges: list[list[int]] = []
    for h in hours:
        if h.aqi is None or h.aqi < threshold:
            continue
        lo, hi = max(h.hour * 60, day_start), min((h.hour + 1) * 60, day_end)
        if ranges and ranges[-1][1] == lo:
            ranges[-1][1] = hi
        else:
            ranges.append([lo, hi])
    return [[fmt_time(a), fmt_time(b)] for a, b in ranges]


def plan_day(school: School, readings: list[HourReading], rules: Rules, day: date, mode: str) -> DayPlan:
    air = _Air(readings)
    school_hours = air.hours(school.day_start, school.day_end)
    known = [h for h in school_hours if h.aqi is not None]
    worst = max(known, key=lambda h: h.aqi) if known else None
    cleanest = min(known, key=lambda h: (h.aqi, h.hour)) if known else None

    outdoor_times = [(b.start, b.end) for b in school.blocks if b.outdoor]
    taken: list[tuple[int, int]] = []
    blocks: list[BlockPlan] = []

    for block in school.blocks:
        when = f"{fmt_time(block.start)}–{fmt_time(block.end)}"
        aqi = air.window(block.start, block.end)
        bp = BlockPlan(
            name=block.name,
            start=fmt_time(block.start),
            end=fmt_time(block.end),
            students=block.students,
            outdoor=block.outdoor,
            action="keep",
            aqi=aqi,
        )
        blocks.append(bp)

        if not block.outdoor:
            bp.reason = f"{block.name} {when}: indoors already"
            continue
        if aqi is None:
            bp.reason = f"{block.name} {when}: no forecast for this hour, no change"
            continue
        if rules.band_for(aqi).outdoor == "keep":
            bp.reason = _with_note(f"{block.name} {when} stays outdoors: {AQI_LABEL} {aqi}", rules, aqi)
            continue

        target = None
        if block.can_move:
            busy = [t for t in outdoor_times if t != (block.start, block.end)] + taken
            target = _best_window(block, school, air, rules, busy)

        if target and target[1] <= rules.max_target_aqi:
            new_start, new_aqi = target
            new_end = new_start + (block.end - block.start)
            taken.append((new_start, new_end))
            bp.action = "reschedule"
            bp.new_start, bp.new_end, bp.new_aqi = fmt_time(new_start), fmt_time(new_end), new_aqi
            bp.reason = _with_note(
                f"{block.name} {fmt_time(block.start)} → {fmt_time(new_start)}: {AQI_LABEL} {aqi} → {new_aqi}",
                rules,
                new_aqi,
            )
        else:
            bp.action = "indoors"
            bp.reason = f"{block.name} indoors: {AQI_LABEL} {aqi} at {fmt_time(block.start)}"
            if target:
                bp.reason += (
                    f"; cleanest free slot {fmt_time(target[0])} is still {target[1]}"
                    f" (above {rules.max_target_aqi})"
                )

        if aqi >= rules.impact_min_aqi:
            bp.child_hours = round(block.students * (block.end - block.start) / 60, 1)

    advisories: list[str] = []
    windows = _ranges(school_hours, rules.windows_closed_min_aqi, school.day_start, school.day_end)
    if windows:
        spans = ", ".join(f"{a}–{b}" for a, b in windows)
        advisories.append(f"Keep classroom windows closed {spans} ({AQI_LABEL} {rules.windows_closed_min_aqi}+).")

    commute = air.hours(school.day_start - rules.commute_minutes, school.day_start) + air.hours(
        school.day_end, school.day_end + rules.commute_minutes
    )
    commute = [h for h in commute if h.aqi is not None]
    if commute:
        worst_commute = max(commute, key=lambda h: h.aqi)
        if worst_commute.aqi >= rules.masks_min_aqi:
            advisories.append(f"Masks on the commute: {AQI_LABEL} {worst_commute.aqi} around {worst_commute.time}.")

    if worst and worst.aqi >= rules.grap_min_aqi:
        advisories.append(rules.grap_text)

    moved = [b for b in blocks if b.action in ("indoors", "reschedule")]
    return DayPlan(
        school_id=school.id,
        school_name=school.name,
        date=day.isoformat(),
        mode=mode,
        aqi_label=AQI_LABEL,
        day_start=fmt_time(school.day_start),
        day_end=fmt_time(school.day_end),
        hours=school_hours,
        worst=worst,
        cleanest=cleanest,
        day_band=rules.band_for(worst.aqi).id if worst else None,
        blocks=blocks,
        windows_closed=windows,
        advisories=advisories,
        child_hours_protected=round(sum(b.child_hours for b in blocks), 1),
        blocks_moved=len(moved),
    )
