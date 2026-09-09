from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import requests


TICKERS_PATH = Path("data/tickers.csv")
OUTPUT_PATH = Path("data/price_signals.csv")
BASE_URL = "https://finnhub.io/api/v1/stock/metric"


def load_tickers(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Ticker file not found: {path}")

    df = pd.read_csv(path)
    if "symbol" not in df.columns:
        raise ValueError("data/tickers.csv must contain a 'symbol' column")

    symbols = (
        df["symbol"]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
        .tolist()
    )
    return [s for s in symbols if s]


def fetch_symbol_metrics(symbol: str, api_key: str) -> dict:
    params = {
        "symbol": symbol,
        "metric": "all",
        "token": api_key,
    }

    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    metrics = data.get("metric", {}) or {}
    current_price = metrics.get("currentEv/freeCashFlowTTM")

    row = {
        "symbol": symbol,
        "as_of_date": pd.Timestamp.utcnow().date().isoformat(),
        "current_price": None,
        "high_52w": metrics.get("52WeekHigh"),
        "low_52w": metrics.get("52WeekLow"),
        "52w_return_pct": metrics.get("52WeekPriceReturnDaily"),
        "dist_from_high_52w_pct": None,
    }

    quote_price = None
    if "52WeekHigh" in metrics and "52WeekLow" in metrics:
        quote_price = None

    return row


def fetch_quote(symbol: str, api_key: str) -> float | None:
    url = "https://finnhub.io/api/v1/quote"
    params = {
        "symbol": symbol,
        "token": api_key,
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    current_price = data.get("c")
    if current_price in (None, 0):
        return None
    return float(current_price)


def build_row(symbol: str, api_key: str) -> dict:
    params = {
        "symbol": symbol,
        "metric": "all",
        "token": api_key,
    }
    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    metrics = data.get("metric", {}) or {}
    current_price = fetch_quote(symbol, api_key)
    high_52w = metrics.get("52WeekHigh")
    low_52w = metrics.get("52WeekLow")
    return_52w = metrics.get("52WeekPriceReturnDaily")

    dist_from_high = None
    if current_price is not None and high_52w not in (None, 0):
        dist_from_high = round((float(high_52w) - float(current_price)) / float(high_52w) * 100, 2)

    return {
        "symbol": symbol,
        "as_of_date": pd.Timestamp.utcnow().date().isoformat(),
        "current_price": current_price,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "52w_return_pct": return_52w,
        "dist_from_high_52w_pct": dist_from_high,
    }


def main() -> None:
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        raise EnvironmentError("FINNHUB_API_KEY is not set")

    symbols = load_tickers(TICKERS_PATH)
    rows = []

    for symbol in symbols:
        try:
            row = build_row(symbol, api_key)
            rows.append(row)
        except Exception as exc:
            rows.append(
                {
                    "symbol": symbol,
                    "as_of_date": pd.Timestamp.utcnow().date().isoformat(),
                    "current_price": None,
                    "high_52w": None,
                    "low_52w": None,
                    "52w_return_pct": None,
                    "dist_from_high_52w_pct": None,
                    "error": str(exc),
                }
            )

    df = pd.DataFrame(rows)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)


if __name__ == "__main__":
    main()
