import pandas as pd

from app import format_signal_columns_for_display


def test_format_signal_columns_for_display_rounds_values_and_formats_bool():
    df = pd.DataFrame([
        {
            "Symbol": "GOVT",
            "CurrentPriceSignal": 101.234,
            "High52W": 104.567,
            "DistFromHigh52WPct": 2.345,
            "Near52WeekHigh": True,
        },
        {
            "Symbol": "XYZ",
            "CurrentPriceSignal": None,
            "High52W": None,
            "DistFromHigh52WPct": None,
            "Near52WeekHigh": False,
        },
    ])

    result = format_signal_columns_for_display(df)

    assert result.loc[0, "CurrentPriceSignal"] == "$101.23"
    assert result.loc[0, "High52W"] == "$104.57"
    assert result.loc[0, "DistFromHigh52WPct"] == "2.35%"
    assert result.loc[0, "Near52WeekHigh"] == "Yes"
    assert result.loc[1, "CurrentPriceSignal"] == "—"
    assert result.loc[1, "Near52WeekHigh"] == "No"
