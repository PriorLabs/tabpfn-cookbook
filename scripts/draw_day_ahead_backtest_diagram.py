#!/usr/bin/env python3
"""Draw the backtest diagram of the tabpfn_vs_chronos_power_prices cookbook.

Run: uv run --with matplotlib --with pandas python scripts/draw_day_ahead_backtest_diagram.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "visuals" / "tabpfn_vs_chronos_power_prices" / "backtest.png"

BLUE, RED, GREEN, ORANGE = "#4E79A7", "#E15759", "#59A14F", "#F28E2B"
GREY, INK, MUTED = "#BBBBBB", "#333333", "#777777"
TEST_WEEKS = pd.date_range("2017-01-16", periods=12, freq="28D")

# The lower panel is a schematic: one unit is about a day, and the history bar and the
# gaps between test weeks are not to scale.
DAY_WIDTH, WEEK_STEP, FIRST_CUT, RIGHT_EDGE = 0.26, 2.3, 5.0, 12.4


def draw_year(ax: plt.Axes) -> None:
    """The year 2017 with the 12 numbered test weeks."""
    year_start = pd.Timestamp("2017-01-01")
    ax.barh(0, 365, left=0, height=0.5, color="#EEEEEE")
    for number, week in enumerate(TEST_WEEKS, start=1):
        left = (week - year_start).days
        ax.barh(0, 7, left=left, height=0.5, color=ORANGE)
        ax.text(left + 3.5, 0.62, str(number), ha="center", va="center", fontsize=9, color=INK,
                fontweight="bold" if number <= 3 else "normal")
    for month in pd.date_range(year_start, periods=12, freq="MS"):
        ax.text((month - year_start).days + 15, -0.4, f"{month:%b}", ha="center", va="bottom", fontsize=9, color=MUTED)
    ax.text(0, -1.25, "The test: 12 weeks of 2017, one every four weeks (84 delivery days)",
            fontsize=11, color=INK, fontweight="bold")
    ax.set(xlim=(-52, 372), ylim=(1.3, -1.7))
    ax.axis("off")


def draw_weeks(ax: plt.Axes) -> None:
    """The first three test weeks: known history, seven one-day forecasts, and what is not yet known."""
    week_width = 7 * DAY_WIDTH
    for row, week in enumerate(TEST_WEEKS[:3]):
        cut = FIRST_CUT + WEEK_STEP * row
        ax.barh(row, cut - 0.6, left=0.6, height=0.56, color=BLUE)
        for i, letter in enumerate("MTWTFSS"):
            ax.barh(row, DAY_WIDTH, left=cut + i * DAY_WIDTH, height=0.56, color=RED, edgecolor="white", linewidth=1)
            ax.text(cut + (i + 0.5) * DAY_WIDTH, row, letter, ha="center", va="center", color="white",
                    fontsize=8, fontweight="bold")
        ax.barh(row + 0.4, week_width, left=cut, height=0.16, color=GREEN)
        ax.barh(row, RIGHT_EDGE - cut - week_width, left=cut + week_width, height=0.56, color="none",
                edgecolor=GREY, hatch="///", linewidth=0)
        ax.text(0.45, row, f"Test week {row + 1}\n{week:%d %b} – {week + pd.Timedelta(days=6):%d %b}",
                ha="right", va="center", fontsize=10.5, color=INK)
    ax.text(0.8, 0, "Known prices (history)", va="center", color="white", fontsize=10.5)
    ax.text(RIGHT_EDGE - 0.15, 0, "not yet known", ha="right", va="center", color="#666666", fontsize=10,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 2})
    ax.annotate(
        "7 forecasts, one per day:\neach sees prices up to 23:00 the day before\nand forecasts the next 24 hourly prices",
        xy=(FIRST_CUT + week_width / 2, -0.3), xytext=(FIRST_CUT + week_width / 2, -0.95),
        ha="center", va="center", fontsize=10, color=RED, arrowprops={"arrowstyle": "-", "color": RED},
    )
    ax.annotate(
        "Also known: load and wind+solar\nforecasts for each delivery day",
        xy=(FIRST_CUT + 2 * WEEK_STEP + 6 * DAY_WIDTH, 2.5), xytext=(FIRST_CUT + 2 * WEEK_STEP + 2.4, 3.05),
        fontsize=10, color=GREEN, va="center", arrowprops={"arrowstyle": "-", "color": GREEN},
    )
    ax.text(0.45, 3.05, "… and so on for all 12 weeks", ha="left", va="center", fontsize=10, color=MUTED)
    ax.set(xlim=(-1.9, RIGHT_EDGE), ylim=(3.4, -1.45))
    ax.axis("off")


def main() -> None:
    fig, (year_ax, weeks_ax) = plt.subplots(2, 1, figsize=(12, 5.8), height_ratios=[1, 3.6])
    draw_year(year_ax)
    draw_weeks(weeks_ax)
    fig.tight_layout()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=160, facecolor="white")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
