from io import StringIO

from engine import decide, load_fidelity_csv


def sample_csv():
    return StringIO(
        '''"Symbol","Acquired","Term","DollarGainLoss","PercentGainLoss","CurrentValue","Quantity","AverageCostBasis","CostBasisTotal"
"FDLXX","Sep-01-2026","Short","+$0.00","+0.00%","$1,000.00","1000","$1.00","$1,000.00"
"VTEB","Apr-09-2025","Long","+$200.00","+3.33%","$6,000.00","120","$48.33","$5,800.00"
"AAPL","Jul-02-2019","Long","+$2,000.00","+66.67%","$5,000.00","10","$300.00","$3,000.00"
"GOVT","Jun-12-2026","Short","-$600.00","-6.00%","$9,400.00","400","$25.00","$10,000.00"
'''
    )


def harvest_only_csv():
    return StringIO(
        '''"Symbol","Acquired","Term","DollarGainLoss","PercentGainLoss","CurrentValue","Quantity","AverageCostBasis","CostBasisTotal"
"FDLXX","Sep-01-2026","Short","+$0.00","+0.00%","$8,000.00","8000","$1.00","$8,000.00"
"GOVT","Jun-12-2026","Short","-$800.00","-7.50%","$9,200.00","400","$25.00","$10,000.00"
'''
    )


def base_config():
    return {
        "cash_tickers": ["FDLXX"],
        "cash": {"floor": 5000, "target": 6000, "ceiling": 10000},
        "tax": {"ltcg_target": 3000, "realized_ltcg_ytd": 500, "lt_rate": 0.15, "st_rate": 0.32},
        "harvest": {"min_loss_dollars": 500, "min_loss_pct": 5},
        "sell": {"partial_last_lot": True, "avoid_short_term": False, "max_lots": 8, "prefer_long_term": True},
    }


def test_load_fidelity_csv_parses_required_columns():
    df = load_fidelity_csv(sample_csv())
    assert "symbol" in df.columns
    assert "current_value" in df.columns
    assert len(df) == 4


def test_bank_profits_prefers_low_tax_cost_long_term_lot():
    result = decide(sample_csv(), config=base_config(), market_strong=False)
    assert result["action"] == "bank_profits"
    assert round(result["amount_needed"], 2) == 5000.00
    assert not result["sell_plan"].empty
    first = result["sell_plan"].iloc[0]
    assert first["symbol"] == "VTEB"
    assert round(first["estimated_proceeds"], 2) == 5000.00


def test_harvest_only_when_cash_is_in_range():
    result = decide(harvest_only_csv(), config=base_config(), market_strong=False)
    assert result["action"] == "harvest_losses"
    assert result["sell_plan"].empty
    assert not result["harvest_candidates"].empty


def test_missing_cash_ticker_warns_and_treats_cash_as_zero():
    cfg = base_config()
    cfg["cash_tickers"] = ["FDLXX"]
    csv_no_cash = StringIO(
        '''"Symbol","Acquired","Term","DollarGainLoss","PercentGainLoss","CurrentValue","Quantity","AverageCostBasis","CostBasisTotal"
"VTEB","Apr-09-2025","Long","+$200.00","+3.33%","$6,000.00","120","$48.33","$5,800.00"
'''
    )
    result = decide(csv_no_cash, config=cfg, market_strong=False)
    assert result["current_cash"] == 0.0
    assert result["warnings"]