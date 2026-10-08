from datetime import date, datetime

from saans.forecast import HourReading
from saans.planner import plan_day
from saans.rules import load_rules
from saans.schools import Block, School, to_minutes

DAY = date(2024, 11, 18)

# PM2.5 concentrations with exact sub-indices
AQI_50, AQI_101, AQI_200, AQI_201, AQI_301, AQI_401 = 30, 61, 90, 91, 121, 251
PM25_FOR_230 = 100  # 201 + 99/29 * 9 = 231.7 -> 232


def block(name, start, end, students, can_move, outdoor=True):
    return Block(name, to_minutes(start), to_minutes(end), outdoor, can_move, students)


SCHOOL = School(
    id="t-1",
    join_code="T1",
    name="Test School",
    area="Test",
    lat=0,
    lon=0,
    students=1000,
    day_start=to_minutes("07:30"),
    day_end=to_minutes("13:30"),
    blocks=(
        block("Assembly", "07:40", "08:00", 1000, False),
        block("PE A", "08:00", "08:40", 120, True),
        block("PE B", "09:20", "10:00", 90, True),
    ),
)


def readings(by_hour: dict[int, float], default: float) -> list[HourReading]:
    return [
        HourReading(datetime(2024, 11, 18, h), by_hour.get(h, default), None) for h in range(24)
    ]


def plan(by_hour, default):
    return plan_day(SCHOOL, readings(by_hour, default), load_rules(), DAY, "replay")


def actions(p):
    return {b.name: b.action for b in p.blocks}


def test_clean_day_keeps_everything():
    p = plan({}, AQI_50)
    assert set(actions(p).values()) == {"keep"}
    assert p.child_hours_protected == 0
    assert p.advisories == []
    assert p.blocks[0].reason == "Assembly 7:40–8:00 stays outdoors: AQI (est.) 50"


def test_moderate_keeps_outdoors_with_sensitive_note():
    p = plan({}, AQI_101)
    assert set(actions(p).values()) == {"keep"}
    assert "sensitive children take it easy" in p.blocks[1].reason


def test_poor_morning_moves_pe_and_assembly_indoors():
    p = plan({7: AQI_201, 8: AQI_201, 9: AQI_201, 12: AQI_50}, AQI_101)
    a = actions(p)
    assert a["Assembly"] == "indoors"
    assert a["PE A"] == "reschedule"
    pe = p.blocks[1]
    assert pe.reason == "PE A 8:00 → 12:00: AQI (est.) 201 → 50"
    assert (pe.new_start, pe.new_end, pe.new_aqi) == ("12:00", "12:40", 50)


def test_reschedule_quotes_numbers_and_never_targets_above_200():
    p = plan({h: AQI_301 for h in range(7, 11)}, AQI_200)
    for b in p.blocks:
        if b.action == "reschedule":
            assert b.new_aqi <= 200
            assert "→" in b.reason and str(b.aqi) in b.reason and str(b.new_aqi) in b.reason


def test_pe_goes_indoors_when_cleanest_window_is_above_200():
    p = plan({}, PM25_FOR_230)
    pe = p.blocks[1]
    assert pe.action == "indoors"
    assert "above 200" in pe.reason


def test_moved_blocks_do_not_collide():
    p = plan({7: AQI_301, 8: AQI_301, 9: AQI_301, 12: AQI_50, 13: AQI_50}, AQI_301)
    moved = [b for b in p.blocks if b.action == "reschedule"]
    assert len(moved) == 2
    spans = sorted((to_minutes(b.new_start), to_minutes(b.new_end)) for b in moved)
    assert spans[0][1] <= spans[1][0]
    for b in moved:
        for other in SCHOOL.blocks:
            assert not (to_minutes(b.new_start) < other.end and other.start < to_minutes(b.new_end))


def test_impact_counts_students_times_duration():
    p = plan({h: AQI_301 for h in range(7, 11)}, AQI_50)
    # Assembly 1000 x 20 min + PE A 120 x 40 min + PE B 90 x 40 min
    assert p.child_hours_protected == round(1000 / 3, 1) + 80 + 60
    assert p.blocks_moved == 3


def test_very_poor_closes_windows_and_masks():
    p = plan({8: AQI_301, 9: AQI_301, 7: AQI_301}, AQI_101)
    assert p.windows_closed == [["7:30", "10:00"]]
    assert any(a.startswith("Masks on the commute") for a in p.advisories)
    assert not any("GRAP" in a for a in p.advisories)


def test_severe_adds_grap_check():
    p = plan({}, AQI_401)
    assert any("GRAP / CAQM" in a for a in p.advisories)
    assert p.day_band == "severe"
    assert set(actions(p).values()) == {"indoors"}


def test_worst_and_cleanest_hours():
    p = plan({8: AQI_401, 12: AQI_50}, AQI_101)
    assert (p.worst.hour, p.worst.aqi) == (8, 401)
    assert (p.cleanest.hour, p.cleanest.aqi) == (12, 50)
    assert [h.hour for h in p.hours] == list(range(7, 14))
