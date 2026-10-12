"""Rebuild the committed Favorita teaching panel if it is absent.

Run on a CPU worker with the hierarchical cookbook requirements installed.
"""
from pathlib import Path
import pandas as pd
from huggingface_hub import hf_hub_download

STORES = list(range(1, 13))
FAMILIES = ["BEVERAGES", "BREAD/BAKERY", "CLEANING", "GROCERY I"]
DATASET = "t4tiana/store-sales-time-series-forecasting"
REVISION = "1ac138dfdfafc520bc29831e73373954b1b7bc05"
panel_path = Path(__file__).resolve().parents[1] / "datasets/forecast_hierarchical_series/favorita_daily.csv"

if not panel_path.exists():
    def source_file(name):
        return hf_hub_download(DATASET, name, repo_type="dataset", revision=REVISION)

    chunks = pd.read_csv(source_file("train.csv"), parse_dates=["date"], chunksize=250_000)
    selected = []
    for chunk in chunks:
        keep = (chunk.store_nbr.isin(STORES) & chunk.family.isin(FAMILIES)
                & chunk.date.ge("2015-04-01"))
        selected.append(chunk.loc[keep, ["date", "store_nbr", "family", "sales", "onpromotion"]])
    panel = pd.concat(selected, ignore_index=True)
    stores = pd.read_csv(source_file("stores.csv"))
    panel = panel.merge(stores[["store_nbr", "city", "state", "type", "cluster"]],
                        on="store_nbr", validate="many_to_one")
    holidays = pd.read_csv(source_file("holidays_events.csv"), parse_dates=["date"])
    holidays = holidays.loc[~holidays.transferred & holidays.type.isin(
        ["Holiday", "Additional", "Bridge", "Transfer"])]
    panel["is_holiday"] = 0
    for holiday in holidays.itertuples():
        applies = panel.date.eq(holiday.date)
        if holiday.locale == "Regional":
            applies &= panel.state.eq(holiday.locale_name)
        elif holiday.locale == "Local":
            applies &= panel.city.eq(holiday.locale_name)
        panel.loc[applies, "is_holiday"] = 1
    panel["series_id"] = panel.store_nbr.astype(str) + " / " + panel.family
    panel.sort_values(["series_id", "date"]).to_csv(panel_path, index=False)

