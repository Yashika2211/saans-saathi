import copy

import pytest
import yaml

from saans.rules import RULES_PATH, load_rules, parse_rules


@pytest.mark.parametrize(
    "aqi, band, outdoor",
    [(0, "satisfactory", "keep"), (100, "satisfactory", "keep"), (101, "moderate", "keep"),
     (200, "moderate", "keep"), (201, "poor", "move"), (300, "poor", "move"),
     (301, "very_poor", "move"), (400, "very_poor", "move"), (401, "severe", "move"),
     (500, "severe", "move")],
)
def test_band_edges(aqi, band, outdoor):
    b = load_rules().band_for(aqi)
    assert (b.id, b.outdoor) == (band, outdoor)


def test_thresholds_come_from_config():
    rules = load_rules()
    assert rules.max_target_aqi == 200
    assert rules.windows_closed_min_aqi == 301
    assert rules.masks_min_aqi == 301
    assert rules.grap_min_aqi == 401
    assert "GRAP" in rules.grap_text


def _raw():
    return yaml.safe_load(RULES_PATH.read_text())


def test_rejects_gap_between_bands():
    raw = copy.deepcopy(_raw())
    raw["bands"][1]["min"] = 102
    with pytest.raises(ValueError, match="gap"):
        parse_rules(raw)


def test_rejects_unknown_outdoor_action():
    raw = copy.deepcopy(_raw())
    raw["bands"][2]["outdoor"] = "cancel"
    with pytest.raises(ValueError, match="keep or move"):
        parse_rules(raw)
