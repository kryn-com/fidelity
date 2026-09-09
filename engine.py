from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml


REQUIRED_COLUMNS = [
    "Symbol",
    "Acquired",
    "Term",
    "DollarGainLoss",
    "PercentGainLoss",
    "CurrentValue",
    "Quantity",
    "AverageCostBasis",
    "CostBasisTotal",
]


def load_config(path: str | Path = "config.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_money(value: Any) -> float:
    if pd.isna(value):
        return 0.0
    s = str(value).strip().replace("$", "").replace(",", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    s = s.replace("+", "")
    return float(s)


def _parse_percent(value: Any) -> float:
    if pd.isna(value):
        return 0.0
    s = str(value).strip().replace("%", "").replace(",", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    s = s.replace("+", "")
    return float(s)


def load_fidelity_csv(source: str | Path | Any) -> pd.DataFrame:
    df = pd.read_csv(source)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df.copy()
    df["Acquired"] = pd.to_datetime(df["Acquired"], format="%b-%d-%Y", errors="coerce")
    df["DollarGainLoss"] = df["DollarGainLoss"].apply(_parse_money)
    df["PercentGainLoss"] = df["PercentGainLoss"].apply(_parse_percent)
    df["CurrentValue"] = df["CurrentValue"].apply(_parse_money)
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0.0)
    df["AverageCostBasis"] = df["AverageCostBasis"].apply(_parse_money)
    df["CostBasisTotal"] = df["CostBasisTotal"].apply(_parse_money)

    return df


def get_active_funding_rule(review_date: pd.Timestamp, config: Dict[str, Any]) -> Dict[str, Any]:
    rules = config["funding_targets"]["as_of_rules"]
    for rule in rules:
        start = pd.Timestamp(rule["start_date"])
        end = pd.Timestamp(rule["end_date"])
        if start <= review_date.normalize() <= end:
            return rule
    raise ValueError(f"No funding rule found for review date {review_date.date()}")


def identify_cash_bucket_rows(lots: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
    aliases = config["cash_bucket"].get("target_ticker_aliases", [])
    aliases = {str(x).upper() for x in aliases}
    return lots[lots["Symbol"].astype(str).str.upper().isin(aliases)].copy()


def identify_cash_like_rows(lots: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
    symbols = config.get("cash_like_sources", {}).get("enabled_symbols", [])
    symbols = {str(x).upper() for x in symbols}
    return lots[lots["Symbol"].astype(str).str.upper().isin(symbols)].copy()


def identify_harvest_candidates(lots: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
    harvest_cfg = config.get("harvest", {})
    if not harvest_cfg.get("enabled", False):
        return lots.iloc[0:0].copy()

    min_loss_dollars = float(harvest_cfg.get("min_loss_dollars", 500))
    min_loss_pct = float(harvest_cfg.get("min_loss_pct", 5.0))

    mask = (
        (lots["DollarGainLoss"] <= -min_loss_dollars)
        & (lots["PercentGainLoss"] <= -min_loss_pct)
    )
    return lots[mask].copy()


def add_tax_fields(lots: pd.DataFrame, config: Dict[str, Any], review_date: pd.Timestamp) -> pd.DataFrame:
    lots = lots.copy()

    lt_rate = float(config["tax"].get("lt_rate", 0.15))
    st_rate = float(config["tax"].get("st_rate", 0.32))
    threshold_days = int(config.get("lot_selection", {}).get("days_to_long_term_threshold", 30))

    lots["IsLongTerm"] = lots["Term"].astype(str).str.lower().eq("long")
    lots["EstimatedTaxRate"] = lots["IsLongTerm"].map({True: lt_rate, False: st_rate})

    gains_only = lots["DollarGainLoss"].clip(lower=0)
    lots["EstimatedTaxCost"] = gains_only * lots["EstimatedTaxRate"]

    current_value_nonzero = lots["CurrentValue"].replace(0, pd.NA)
    lots["TaxCostPerDollarRaised"] = (lots["EstimatedTaxCost"] / current_value_nonzero).fillna(0.0)

    lots["DaysHeld"] = (review_date.normalize() - lots["Acquired"]).dt.days
    lots["DaysToLongTerm"] = (365 - lots["DaysHeld"]).clip(lower=0)
    lots["NearLongTerm"] = (~lots["IsLongTerm"]) & (lots["DaysToLongTerm"] <= threshold_days)

    return lots


def calculate_funding_need(
    current_fdlxx_balance: float,
    review_date: pd.Timestamp,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    rule = get_active_funding_rule(review_date, config)
    floor = float(rule["floor"])
    target = float(rule["target"])
    ceiling = float(rule["ceiling"])

    amount_needed = max(0.0, target - current_fdlxx_balance)

    if current_fdlxx_balance < floor:
        status = "below_floor"
    elif current_fdlxx_balance < target:
        status = "below_target"
    elif current_fdlxx_balance <= ceiling:
        status = "within_band"
    else:
        status = "above_ceiling"

    return {
        "review_date": review_date,
        "rule": rule,
        "floor": floor,
        "target": target,
        "ceiling": ceiling,
        "current_cash": float(current_fdlxx_balance),
        "amount_needed": float(amount_needed),
        "status": status,
    }


def rank_cash_like_conversions(
    cash_like_rows: pd.DataFrame,
    config: Dict[str, Any],
) -> pd.DataFrame:
    if cash_like_rows.empty:
        return cash_like_rows.copy()

    ranked = cash_like_rows.copy()
    priority_order = config.get("cash_like_sources", {}).get("priority_order", [])
    priority_map = {symbol.upper(): i for i, symbol in enumerate(priority_order)}

    ranked["PriorityRank"] = ranked["Symbol"].astype(str).str.upper().map(priority_map).fillna(999)
    ranked = ranked.sort_values(
        by=["PriorityRank", "EstimatedTaxCost", "CurrentValue"],
        ascending=[True, True, False],
    ).reset_index(drop=True)
    return ranked


def _add_proposed_sale_fields(plan: pd.DataFrame) -> pd.DataFrame:
    if plan.empty:
        plan = plan.copy()
        if "ProposedSellValue" not in plan.columns:
            plan["ProposedSellValue"] = pd.Series(dtype="float64")
        plan["ProposedSaleFraction"] = pd.Series(dtype="float64")
        plan["EstimatedRealizedGainForProposedSale"] = pd.Series(dtype="float64")
        plan["EstimatedTaxCostForProposedSale"] = pd.Series(dtype="float64")
        return plan

    plan = plan.copy()
    current_value_nonzero = plan["CurrentValue"].replace(0, pd.NA)
    plan["ProposedSaleFraction"] = (plan["ProposedSellValue"] / current_value_nonzero).fillna(0.0)
    plan["EstimatedRealizedGainForProposedSale"] = (
        plan["DollarGainLoss"] * plan["ProposedSaleFraction"]
    ).fillna(0.0)
    plan["EstimatedTaxCostForProposedSale"] = (
        plan["EstimatedTaxCost"] * plan["ProposedSaleFraction"]
    ).fillna(0.0)
    return plan


def select_cash_like_conversions(
    cash_like_rows: pd.DataFrame,
    amount_needed: float,
    current_cash: float,
    cash_ceiling: float,
    config: Dict[str, Any],
) -> Tuple[pd.DataFrame, float]:
    if cash_like_rows.empty or amount_needed <= 0:
        empty = cash_like_rows.iloc[0:0].copy()
        if "ProposedSellValue" not in empty.columns:
            empty["ProposedSellValue"] = pd.Series(dtype="float64")
        empty = _add_proposed_sale_fields(empty)
        return empty, amount_needed

    max_ltcg = float(config.get("cash_like_sources", {}).get("max_conversion_ltcg_dollars", 1000))
    allow_partial = bool(config.get("cash_like_sources", {}).get("allow_partial_conversion", True))

    ranked = rank_cash_like_conversions(cash_like_rows, config).copy()
    ranked["LotGainLossFullPosition"] = ranked["DollarGainLoss"]
    ranked["ProposedSellValue"] = 0.0

    selected_rows = []
    remaining = float(amount_needed)
    running_positive_gains = 0.0
    running_cash_after_sales = float(current_cash)

    for _, row in ranked.iterrows():
        value = float(row["CurrentValue"])
        full_position_gain = float(row["LotGainLossFullPosition"])
        realized_positive_gain = max(0.0, full_position_gain)

        if running_positive_gains + realized_positive_gain > max_ltcg and remaining > 0:
            continue

        if allow_partial:
            if running_cash_after_sales + value <= cash_ceiling:
                proposed = value
            else:
                proposed = min(value, remaining)
        else:
            proposed = value

        if proposed <= 0:
            continue

        new_row = row.copy()
        new_row["ProposedSellValue"] = proposed
        selected_rows.append(new_row)

        proportion = proposed / value if value > 0 else 0.0
        running_positive_gains += realized_positive_gain * proportion
        running_cash_after_sales += proposed
        remaining = max(0.0, amount_needed - sum(float(r["ProposedSellValue"]) for r in selected_rows))

        if remaining <= 0:
            break

    if selected_rows:
        selected = pd.DataFrame(selected_rows).reset_index(drop=True)
    else:
        selected = ranked.iloc[0:0].copy()

    selected = _add_proposed_sale_fields(selected)
    return selected, remaining


def rank_sale_candidates(
    lots: pd.DataFrame,
    config: Dict[str, Any],
) -> pd.DataFrame:
    if lots.empty:
        return lots.copy()

    cash_bucket_aliases = {
        str(x).upper()
        for x in config.get("cash_bucket", {}).get("target_ticker_aliases", [])
    }
    cash_like_symbols = {
        str(x).upper()
        for x in config.get("cash_like_sources", {}).get("enabled_symbols", [])
    }

    candidates = lots.copy()
    candidates = candidates[
        ~candidates["Symbol"].astype(str).str.upper().isin(cash_bucket_aliases | cash_like_symbols)
    ].copy()

    avoid_st = bool(config.get("lot_selection", {}).get("avoid_short_term_gains", True))
    if avoid_st:
        candidates = candidates[~((~candidates["IsLongTerm"]) & (candidates["DollarGainLoss"] > 0))].copy()

    candidates["Sort_LongTermFirst"] = (~candidates["IsLongTerm"]).astype(int)
    candidates["Sort_NearLongTermPenalty"] = candidates["NearLongTerm"].astype(int)

    candidates = candidates.sort_values(
        by=[
            "Sort_LongTermFirst",
            "TaxCostPerDollarRaised",
            "Sort_NearLongTermPenalty",
            "CurrentValue",
        ],
        ascending=[True, True, True, False],
    ).reset_index(drop=True)

    return candidates


def select_sale_lots(
    ranked_candidates: pd.DataFrame,
    amount_needed: float,
    config: Dict[str, Any],
) -> Tuple[pd.DataFrame, float]:
    if ranked_candidates.empty or amount_needed <= 0:
        empty = ranked_candidates.iloc[0:0].copy()
        if "ProposedSellValue" not in empty.columns:
            empty["ProposedSellValue"] = pd.Series(dtype="float64")
        empty = _add_proposed_sale_fields(empty)
        return empty, amount_needed

    partial_last_lot = bool(config.get("lot_selection", {}).get("partial_last_lot", True))
    max_lots = int(config.get("lot_selection", {}).get("max_lots", 8))
    min_trade_dollars = float(config.get("lot_selection", {}).get("min_trade_dollars", 250))

    selected_rows = []
    remaining = float(amount_needed)

    for _, row in ranked_candidates.iterrows():
        if len(selected_rows) >= max_lots:
            break

        value = float(row["CurrentValue"])
        if value <= 0:
            continue

        proposed = min(value, remaining) if partial_last_lot else value
        if proposed < min_trade_dollars and remaining > min_trade_dollars:
            continue

        new_row = row.copy()
        new_row["ProposedSellValue"] = proposed
        selected_rows.append(new_row)

        remaining = max(0.0, remaining - proposed)
        if remaining <= 0:
            break

    if selected_rows:
        selected = pd.DataFrame(selected_rows).reset_index(drop=True)
    else:
        selected = ranked_candidates.iloc[0:0].copy()

    selected = _add_proposed_sale_fields(selected)
    return selected, remaining


def summarize_tax_impact(plan: pd.DataFrame) -> Dict[str, float]:
    if plan.empty:
        return {
            "proposed_sell_value": 0.0,
            "estimated_realized_gain": 0.0,
            "estimated_tax_cost": 0.0,
            "estimated_ltcg": 0.0,
            "estimated_stcg": 0.0,
        }

    realized_gain = plan["EstimatedRealizedGainForProposedSale"]
    tax_cost = plan["EstimatedTaxCostForProposedSale"]

    ltcg = realized_gain.where(plan["IsLongTerm"], 0.0).clip(lower=0).sum()
    stcg = realized_gain.where(~plan["IsLongTerm"], 0.0).clip(lower=0).sum()

    return {
        "proposed_sell_value": float(plan["ProposedSellValue"].sum()),
        "estimated_realized_gain": float(realized_gain.sum()),
        "estimated_tax_cost": float(tax_cost.sum()),
        "estimated_ltcg": float(ltcg),
        "estimated_stcg": float(stcg),
    }


def determine_action(
    funding_status: Dict[str, Any],
    cash_like_plan: pd.DataFrame,
    sell_plan: pd.DataFrame,
    harvest_candidates: pd.DataFrame,
) -> str:
    amount_needed = float(funding_status["amount_needed"])
    status = funding_status["status"]

    if amount_needed <= 0 and harvest_candidates.empty:
        return "do_nothing"

    if amount_needed <= 0 and not harvest_candidates.empty:
        return "harvest_losses_only"

    has_cash_like = not cash_like_plan.empty
    has_sell_plan = not sell_plan.empty

    if has_cash_like and not has_sell_plan:
        return "convert_cash_like_to_fdlxx"

    if has_sell_plan and not has_cash_like:
        return "sell_tax_efficient_lots_to_fdlxx"

    if has_cash_like and has_sell_plan:
        return "mixed_action"

    if status in {"below_floor", "below_target"}:
        return "sell_tax_efficient_lots_to_fdlxx"

    return "do_nothing"


def build_review_result(
    holdings: pd.DataFrame,
    funding_status: Dict[str, Any],
    cash_bucket_rows: pd.DataFrame,
    cash_like_rows: pd.DataFrame,
    cash_like_plan: pd.DataFrame,
    sell_plan: pd.DataFrame,
    harvest_candidates: pd.DataFrame,
    warnings: List[str],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    combined_plan = pd.concat([cash_like_plan, sell_plan], ignore_index=True) if (
        not cash_like_plan.empty or not sell_plan.empty
    ) else pd.DataFrame()

    tax_summary = summarize_tax_impact(combined_plan) if not combined_plan.empty else summarize_tax_impact(
        pd.DataFrame(columns=[
            "ProposedSellValue",
            "EstimatedRealizedGainForProposedSale",
            "EstimatedTaxCostForProposedSale",
            "IsLongTerm",
        ])
    )

    action = determine_action(funding_status, cash_like_plan, sell_plan, harvest_candidates)

    return {
        "action": action,
        "review_date": str(pd.Timestamp(funding_status["review_date"]).date()),
        "current_cash": round(float(funding_status["current_cash"]), 2),
        "cash_floor": round(float(funding_status["floor"]), 2),
        "cash_target": round(float(funding_status["target"]), 2),
        "cash_ceiling": round(float(funding_status["ceiling"]), 2),
        "amount_needed": round(float(funding_status["amount_needed"]), 2),
        "cash_status": funding_status["status"],
        "cash_bucket_ticker": config["cash_bucket"]["target_ticker"],
        "cash_bucket_count": int(len(cash_bucket_rows)),
        "cash_like_count": int(len(cash_like_rows)),
        "warnings": warnings,
        "cash_like_plan": cash_like_plan.to_dict(orient="records"),
        "sell_plan": sell_plan.to_dict(orient="records"),
        "harvest_candidates": harvest_candidates.to_dict(orient="records"),
        "tax_summary": {k: round(float(v), 2) for k, v in tax_summary.items()},
    }


def run_review(
    holdings_source: str | Path | Any,
    config: Dict[str, Any],
    review_date: Optional[pd.Timestamp] = None,
    market_strong: bool = False,
) -> Dict[str, Any]:
    review_date = pd.Timestamp.today().normalize() if review_date is None else pd.Timestamp(review_date).normalize()

    lots = load_fidelity_csv(holdings_source)
    lots = add_tax_fields(lots, config, review_date)

    warnings: List[str] = []

    cash_bucket_rows = identify_cash_bucket_rows(lots, config)
    current_cash = float(cash_bucket_rows["CurrentValue"].sum())

    if cash_bucket_rows.empty:
        target = config["cash_bucket"]["target_ticker"]
        warnings.append(f"No rows matched cash bucket ticker aliases for {target}. Cash balance was treated as 0.")

    funding_status = calculate_funding_need(current_cash, review_date, config)

    cash_like_rows = identify_cash_like_rows(lots, config)
    harvest_candidates = identify_harvest_candidates(lots, config)

    cash_like_plan, remaining_need = select_cash_like_conversions(
        cash_like_rows=cash_like_rows,
        amount_needed=funding_status["amount_needed"],
        current_cash=funding_status["current_cash"],
        cash_ceiling=funding_status["ceiling"],
        config=config,
    )

    ranked_sale_candidates = rank_sale_candidates(lots, config)
    sell_plan, final_remaining_need = select_sale_lots(
        ranked_sale_candidates,
        remaining_need,
        config,
    )

    if market_strong and funding_status["status"] == "below_target" and final_remaining_need == 0:
        warnings.append("Market strong override is on, but no extra opportunistic prefunding logic is implemented yet.")

    result = build_review_result(
        holdings=lots,
        funding_status=funding_status,
        cash_bucket_rows=cash_bucket_rows,
        cash_like_rows=cash_like_rows,
        cash_like_plan=cash_like_plan,
        sell_plan=sell_plan,
        harvest_candidates=harvest_candidates,
        warnings=warnings,
        config=config,
    )

    result["remaining_need_after_plan"] = round(float(final_remaining_need), 2)
    return result


def decide(
    holdings_source: str | Path | Any,
    config: Dict[str, Any],
    market_strong: bool = False,
) -> Dict[str, Any]:
    return run_review(
        holdings_source=holdings_source,
        config=config,
        market_strong=market_strong,
    )