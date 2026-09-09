from __future__ import annotations

import copy

import pandas as pd
import streamlit as st

from engine import get_active_funding_rule, load_config, run_review


SIGNAL_DISPLAY_COLUMNS = [
    "CurrentPriceSignal",
    "High52W",
    "DistFromHigh52WPct",
    "Near52WeekHigh",
]


def format_signal_columns_for_display(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    display_df = df.copy()
    for column in SIGNAL_DISPLAY_COLUMNS:
        if column not in display_df.columns:
            continue

        if column == "Near52WeekHigh":
            display_df[column] = display_df[column].map(
                lambda value: "Yes" if pd.notna(value) and bool(value) else "No" if pd.notna(value) else "—"
            )
            continue

        series = pd.to_numeric(display_df[column], errors="coerce")
        display_df[column] = series.map(
            lambda value: "—" if pd.isna(value) else (
                f"${value:,.2f}" if column in {"CurrentPriceSignal", "High52W"} else f"{value:.2f}%"
            )
        )

    return display_df


st.set_page_config(page_title="Taxable Review Tool", layout="wide")
st.title("Taxable Review Tool")

base_config = load_config()
today = pd.Timestamp.today().normalize()
active_rule = get_active_funding_rule(today, base_config)

st.sidebar.header("Review Settings")

cash_ticker = st.sidebar.text_input(
    "Target cash ticker",
    value=base_config["cash_bucket"]["target_ticker"],
)

floor = st.sidebar.number_input(
    "Cash floor",
    min_value=0.0,
    value=float(active_rule["floor"]),
    step=500.0,
)

target = st.sidebar.number_input(
    "Cash target",
    min_value=0.0,
    value=float(active_rule["target"]),
    step=500.0,
)

ceiling = st.sidebar.number_input(
    "Cash ceiling",
    min_value=0.0,
    value=float(active_rule["ceiling"]),
    step=500.0,
)

market_strong = st.sidebar.checkbox("Market strong", value=False)

uploaded_file = st.file_uploader("Upload Fidelity tax-lot CSV", type=["csv"])

if uploaded_file is None:
    st.info("Upload a Fidelity tax-lot CSV to run the review.")
else:
    config = copy.deepcopy(base_config)

    config["cash_bucket"]["target_ticker"] = cash_ticker
    config["cash_bucket"]["target_ticker_aliases"] = [cash_ticker]

    for rule in config["funding_targets"]["as_of_rules"]:
        start = pd.Timestamp(rule["start_date"])
        end = pd.Timestamp(rule["end_date"])
        if start <= today <= end:
            rule["floor"] = float(floor)
            rule["target"] = float(target)
            rule["ceiling"] = float(ceiling)
            break

    result = run_review(
        holdings_source=uploaded_file,
        config=config,
        review_date=today,
        market_strong=market_strong,
    )

    st.subheader("Decision")
    st.write(f"Action: {result['action']}")
    st.write(f"Review date: {result['review_date']}")
    st.write(f"Cash ticker: {result['cash_bucket_ticker']}")
    st.write(f"Current cash: ${result['current_cash']:,.2f}")
    st.write(f"Cash floor: ${result['cash_floor']:,.2f}")
    st.write(f"Cash target: ${result['cash_target']:,.2f}")
    st.write(f"Cash ceiling: ${result['cash_ceiling']:,.2f}")
    st.write(f"Amount needed: ${result['amount_needed']:,.2f}")
    st.write(f"Remaining need after plan: ${result['remaining_need_after_plan']:,.2f}")
    st.write(f"Cash status: {result['cash_status']}")

    if result["warnings"]:
        st.subheader("Warnings")
        for warning in result["warnings"]:
            st.warning(warning)

    st.subheader("Tax summary")
    st.json(result["tax_summary"])

    st.subheader("Cash-like conversion plan")
    if result["cash_like_plan"]:
        cash_like_df = format_signal_columns_for_display(pd.DataFrame(result["cash_like_plan"]))
        st.dataframe(cash_like_df, use_container_width=True)
    else:
        st.write("No cash-like conversions proposed.")

    st.subheader("Sell plan")
    if result["sell_plan"]:
        sell_plan_df = format_signal_columns_for_display(pd.DataFrame(result["sell_plan"]))
        st.dataframe(sell_plan_df, use_container_width=True)
    else:
        st.write("No broader lot sales proposed.")

    st.subheader("Harvest candidates")
    if result["harvest_candidates"]:
        st.dataframe(pd.DataFrame(result["harvest_candidates"]), use_container_width=True)
    else:
        st.write("No harvest candidates found.")