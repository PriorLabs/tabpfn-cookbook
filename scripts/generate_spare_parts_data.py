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
    # id, name, category, base rate, annual amplitude, phase, trend, demand pattern
    ("BRG-6204", "Deep-groove bearing 6204", "Bearings", 24.0, 0.06, 0.2, 0.03, "steady"),
    ("BRG-6305", "Deep-groove bearing 6305", "Bearings", 18.0, 0.10, 0.5, -0.24, "declining"),
    ("FLT-HYD-010", "Hydraulic filter 10 μm", "Filters", 7.0, 0.08, 2.2, 0.02, "replenishment"),
    ("FLT-AIR-220", "Air filter cartridge 220", "Filters", 13.0, 0.55, 2.6, 0.12, "seasonal"),
    ("DRV-BELT-A45", "Drive belt A45", "Drive", 4.5, 0.12, 4.0, 0.05, "campaign"),
    ("DRV-SPR-08", "Drive sprocket 08", "Drive", 2.0, 0.18, 4.4, 0.08, "intermittent"),
]
PLANTS = [("Augsburg", "BY", 1.12), ("Bremen", "HB", 0.88)]


def generate(seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frames: list[pd.DataFrame] = []

    for location, state_code, plant_factor in PLANTS:
        public_holidays = holidays.Germany(years=[2023, 2024], subdiv=state_code)
        for (
            part_id,
            part_name,
            category,
            base_rate,
            annual_amp,
            phase,
            trend_rate,
            pattern,
        ) in PARTS:
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
            if category == "Filters":
                # Filters are consumed during weekend operation too, unlike most parts.
                weekly = np.array([1.02, 1.00, 1.00, 0.98, 0.95, 0.62, 0.45])[day_of_week]
            annual = 1 + annual_amp * np.sin(2 * np.pi * day / 365.25 + phase)
            trend = 1 + trend_rate * day / len(DATES)

            utilisation = np.zeros(len(DATES))
            innovations = rng.normal(0, 0.025, len(DATES))
            for index in range(1, len(DATES)):
                utilisation[index] = 0.90 * utilisation[index - 1] + innovations[index]

            expected = base_rate * plant_factor * weekly * annual * trend
            expected *= np.exp(utilisation)

            if pattern == "replenishment":
                # Hydraulic filters arrive in concentrated eight-week replacement cycles.
                distance = np.minimum((day + 9) % 56, 56 - ((day + 9) % 56))
                expected *= 0.18 + 4.8 * np.exp(-0.5 * (distance / 2.4) ** 2)
            elif pattern == "campaign":
                # Belt replacement is concentrated in short maintenance campaigns.
                expected *= np.where(is_campaign, 4.5, 0.65)

            expected *= np.where(is_holiday, 0.12, 1.0)
            expected *= np.where(is_shutdown, 0.18, 1.0)

            if pattern == "intermittent":
                # Slow-moving sprockets have many zero-demand days and occasional bulk orders.
                order_probability = np.clip(0.10 + expected / 35, 0.08, 0.28)
                orders = rng.random(len(DATES)) < order_probability
                demand = np.zeros(len(DATES), dtype=int)
                demand[orders] = 1 + rng.negative_binomial(2, 0.42, orders.sum())
                bulk_orders = rng.random(len(DATES)) < 0.012
                demand[bulk_orders] += rng.integers(6, 16, bulk_orders.sum())
            else:
                noise_scale = 0.28 if pattern == "steady" else 0.55
                noise = rng.normal(0, noise_scale * np.sqrt(np.maximum(expected, 1)), len(DATES))
                demand = np.rint(np.clip(expected + noise, 0, None)).astype(int)
                spikes = rng.random(len(DATES)) < (0.002 if pattern == "steady" else 0.005)
                demand[spikes] += np.rint(
                    expected[spikes] * rng.uniform(0.5, 1.4, spikes.sum())
                ).astype(int)

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
