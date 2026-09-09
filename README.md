# Taxable Review Tool

Small biweekly review tool for taxable-account lot sales using Fidelity tax-lot CSV exports.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run tests

```powershell
pytest
```

## Run app

```powershell
streamlit run app.py
```

## Biweekly workflow

1. Export the latest Fidelity tax-lot CSV.
2. Start the app.
3. Upload the CSV.
4. Confirm the tracked cash ticker.
5. Review the decision banner.
6. Review the proposed sell list and harvest candidates.
7. If you trade, place the sale in Fidelity using Specific ID.

## V1 limits

- No broker login.
- No order placement.
- No saved review history.
- No wash-sale logic.
- No market-data fetches.
- No full tax forecast engine.