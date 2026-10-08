"""Load the rule thresholds from config/rules.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
RULES_PATH = CONFIG_DIR / "rules.yaml"


@dataclass(frozen=True)
class Band:
    id: str
    min: int
    max: int
    outdoor: str  # "keep" | "move"
    note: str | None = None


@dataclass(frozen=True)
class Rules:
    bands: tuple[Band, ...]
    max_target_aqi: int
    step_minutes: int
    windows_closed_min_aqi: int
    masks_min_aqi: int
    commute_minutes: int
    grap_min_aqi: int
    grap_text: str
    impact_min_aqi: int

    def band_for(self, aqi: int) -> Band:
        for band in self.bands:
            if band.min <= aqi <= band.max:
                return band
        return self.bands[-1] if aqi > self.bands[-1].max else self.bands[0]


def parse_rules(raw: dict) -> Rules:
    bands = tuple(
        Band(id=b["id"], min=int(b["min"]), max=int(b["max"]), outdoor=b["outdoor"], note=b.get("note"))
        for b in raw["bands"]
    )
    for band in bands:
        if band.outdoor not in ("keep", "move"):
            raise ValueError(f"band {band.id}: outdoor must be keep or move, got {band.outdoor!r}")
    for prev, nxt in zip(bands, bands[1:]):
        if nxt.min != prev.max + 1:
            raise ValueError(f"bands {prev.id} and {nxt.id} leave a gap or overlap")
    day = raw["day_actions"]
    return Rules(
        bands=bands,
        max_target_aqi=int(raw["reschedule"]["max_target_aqi"]),
        step_minutes=int(raw["reschedule"]["step_minutes"]),
        windows_closed_min_aqi=int(day["windows_closed"]["min_aqi"]),
        masks_min_aqi=int(day["masks_on_commute"]["min_aqi"]),
        commute_minutes=int(day["masks_on_commute"]["commute_minutes"]),
        grap_min_aqi=int(day["grap_check"]["min_aqi"]),
        grap_text=day["grap_check"]["text"],
        impact_min_aqi=int(raw["impact_min_aqi"]),
    )


@lru_cache(maxsize=1)
def load_rules(path: Path = RULES_PATH) -> Rules:
    return parse_rules(yaml.safe_load(path.read_text()))
