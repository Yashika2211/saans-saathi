"""Demo schools and their timetables from config/schools.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

SCHOOLS_PATH = Path(__file__).resolve().parent.parent / "config" / "schools.json"


@dataclass(frozen=True)
class Block:
    name: str
    start: int  # minutes since midnight
    end: int
    outdoor: bool
    can_move: bool
    students: int


@dataclass(frozen=True)
class School:
    id: str
    join_code: str
    name: str
    area: str
    lat: float
    lon: float
    students: int
    day_start: int
    day_end: int
    blocks: tuple[Block, ...]


class UnknownSchool(KeyError):
    pass


def to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def fmt_time(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d}"


def _parse_school(raw: dict, timetables: dict) -> School:
    tt = timetables[raw["timetable"]]
    total = int(raw["students"])
    blocks = tuple(
        Block(
            name=b["name"],
            start=to_minutes(b["start"]),
            end=to_minutes(b["end"]),
            outdoor=bool(b["outdoor"]),
            can_move=bool(b.get("can_move", False)),
            students=total if b["students"] == "all" else int(b["students"]),
        )
        for b in tt["blocks"]
    )
    return School(
        id=raw["id"],
        join_code=raw["join_code"].upper(),
        name=raw["name"],
        area=raw["area"],
        lat=float(raw["lat"]),
        lon=float(raw["lon"]),
        students=total,
        day_start=to_minutes(tt["school_hours"]["start"]),
        day_end=to_minutes(tt["school_hours"]["end"]),
        blocks=tuple(sorted(blocks, key=lambda b: b.start)),
    )


@lru_cache(maxsize=1)
def load_schools(path: Path = SCHOOLS_PATH) -> dict[str, School]:
    raw = json.loads(path.read_text())
    schools = [_parse_school(s, raw["timetables"]) for s in raw["schools"]]
    return {s.id: s for s in schools}


def get_school(key: str) -> School:
    """Look up a school by id ("demo-1") or join code ("DEMO1")."""
    schools = load_schools()
    if key in schools:
        return schools[key]
    for school in schools.values():
        if school.join_code == key.strip().upper():
            return school
    raise UnknownSchool(key)
