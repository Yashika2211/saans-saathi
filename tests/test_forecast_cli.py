from datetime import date

import pytest

from saans.forecast import ForecastError, get_hourly, parse
from saans.plan import build_plan, main


def test_parse_payload():
    payload = {"hourly": {"time": ["2024-11-18T07:00"], "pm2_5": [143.2], "pm10": [154.0]}}
    (r,) = parse(payload)
    assert (r.time.hour, r.pm25, r.pm10) == (7, 143.2, 154.0)


def test_parse_rejects_empty():
    with pytest.raises(ForecastError):
        parse({"hourly": {}})


def test_replay_fixture_has_24_hours():
    rs = get_hourly(28.6469, 77.3159, date(2024, 11, 18), replay=True, offline=True)
    assert len(rs) == 24


def test_offline_replay_without_cache_fails():
    with pytest.raises(ForecastError):
        get_hourly(1.0, 1.0, date(2024, 1, 1), replay=True, offline=True)


def test_replay_plan_for_demo_school():
    p = build_plan("demo-1", "2024-11-18", offline=True)
    actions = {b.name: b.action for b in p.blocks}
    assert actions["Assembly"] == "indoors"
    assert actions["PE (Classes 6-8)"] == "reschedule"
    assert p.child_hours_protected > 0


def test_cli_prints_plan(capsys):
    assert main(["--school", "DEMO1", "--replay", "2024-11-18", "--offline"]) == 0
    out = capsys.readouterr().out
    assert "MOVE" in out and "Impact:" in out


def test_cli_unknown_school(capsys):
    assert main(["--school", "nope", "--replay", "2024-11-18", "--offline"]) == 2
