#!/usr/bin/env python3
"""Generate deterministic synthetic daily spare-parts demand for the cookbook."""

from __future__ import annotations

import argparse
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "notebooks" / "spare_parts_daily.csv"
DATES = pd.date_range("2023-01-01", "2024-12-31", freq="D")

PARTS = [
    ("BRG-6204", "Deep-groove bearing 6204", "Bearings", 24.0, 0.10, 0.2),
    ("BRG-6305", "Deep-groove bearing 6305", "Bearings", 17.0, 0.12, 0.5),
    ("FLT-HYD-010", "Hydraulic filter 10 μm", "Filters", 14.0, 0.16, 2.2),
    ("FLT-AIR-220", "Air filter cartridge 220", "Filters", 18.0, 0.14, 2.6),
    ("DRV-BELT-A45", "Drive belt A45", "Drive", 12.0, 0.13, 4.0),
    ("DRV-SPR-08", "Drive sprocket 08", "Drive", 8.0, 0.18, 4.4),
]
PLANTS = [("Augsburg", "BY", 1.12), ("Bremen", "HB", 0.88)]


def generate(seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frames: list[pd.DataFrame] = []

    for location, state_code, plant_factor in PLANTS:
        public_holidays = holidays.Germany(years=[2023, 2024], subdiv=state_code)
        for part_id, part_name, category, base_rate, annual_amp, phase in PARTS:
            day = np.arange(len(DATES))
            day_of_week = DATES.dayofweek.to_numpy()
            is_holiday = np.array([date.date() in public_holidays for date in DATES])
            is_shutdown = (
                DATES.isocalendar().week.astype(int).isin([32, 33]).to_numpy()
                | ((DATES.month == 12) & (DATES.day >= 24))
                | ((DATES.month == 1) & (DATES.day <= 2))
            )
            campaign_months = [4, 10] if category == "Bearings" else [3, 9]
            is_campaign = np.isin(DATES.month, campaign_months) & (DATES.day <= 7)

            weekly = np.array([1.08, 1.05, 1.03, 1.00, 0.90, 0.12, 0.07])[day_of_week]
            annual = 1 + annual_amp * np.sin(2 * np.pi * day / 365.25 + phase)
            trend = 1 + rng.uniform(-0.04, 0.07) * day / len(DATES)

            utilisation = np.zeros(len(DATES))
            innovations = rng.normal(0, 0.025, len(DATES))
            for index in range(1, len(DATES)):
                utilisation[index] = 0.90 * utilisation[index - 1] + innovations[index]

            expected = base_rate * plant_factor * weekly * annual * trend
            expected *= np.where(is_campaign, 1.35, 1.0) * np.exp(utilisation)
            expected *= np.where(is_holiday, 0.12, 1.0)
            expected *= np.where(is_shutdown, 0.18, 1.0)

            noise = rng.normal(0, 0.45 * np.sqrt(np.maximum(expected, 1)), len(DATES))
            demand = np.rint(np.clip(expected + noise, 0, None)).astype(int)
            spikes = rng.random(len(DATES)) < 0.003
            demand[spikes] += np.rint(expected[spikes] * rng.uniform(0.5, 1.0, spikes.sum())).astype(int)

            frames.append(
                pd.DataFrame(
                    {
                        "date": DATES,
                        "part_id": part_id,
                        "part_name": part_name,
                        "category": category,
                        "location": location,
                        "state_code": state_code,
                        "is_holiday": is_holiday.astype(int),
                        "is_shutdown": is_shutdown.astype(int),
                        "is_maintenance_campaign": is_campaign.astype(int),
                        "demand": demand,
                    }
                )
            )

    panel = pd.concat(frames, ignore_index=True)
    panel["series_id"] = panel["part_id"] + " · " + panel["location"]
    return panel.sort_values(["series_id", "date"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    data = generate(args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(args.output, index=False)
    print(f"Wrote {len(data):,} rows and {data['series_id'].nunique()} series to {args.output}")


if __name__ == "__main__":
    main()
