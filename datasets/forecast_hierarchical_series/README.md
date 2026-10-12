# Favorita teaching panel

Source: [Store Sales – Time Series Forecasting](https://www.kaggle.com/competitions/store-sales-time-series-forecasting/data), via the [public mirror](https://huggingface.co/datasets/t4tiana/store-sales-time-series-forecasting/tree/1ac138dfdfafc520bc29831e73373954b1b7bc05).

Mirror revision: `1ac138dfdfafc520bc29831e73373954b1b7bc05`.

`favorita_daily.csv` contains stores 1–12 and BEVERAGES, BREAD/BAKERY, CLEANING, and GROCERY I from 2015-04-01 onward. It joins store attributes and holiday flags, respecting local/regional/national scope and transferred holidays. Sales and promotion counts retain their source values. The notebook explains the forecast-time availability assumptions.

SHA-256: `fe76588a94953b61aa8a2285331bdea5fb513a2f8610c1a6e39ea7b42f3bb242`.

The CSV is the exact panel used for the saved notebook outputs. To rebuild a missing copy, run `scripts/prepare_favorita_panel.py` on a CPU worker with `scripts/requirements-hierarchical.txt` installed. Normal notebook execution and feature checks use this committed file without rebuilding it or downloading the full source dataset.
