# Price Signals Handoff — 2026-09-09

## Status

This checkpoint completes the initial lightweight market-signal integration for the taxable review / FDLXX funding workflow.

The completed work now includes:
- daily price-signal generation from Finnhub
- expanded tracked ticker coverage based on current Fidelity holdings
- engine-side merge of signal fields into lot/review output
- Streamlit UI display of signal fields in cash-like and sell-plan tables
- explicit classification of unsupported Finnhub symbols in the updater

This handoff is intended to be the primary resume document for the next development session.

---

## Completed in this checkpoint

### 1. Daily price-signal pipeline
Implemented a daily updater that writes `data/price_signals.csv` from Finnhub data.

Current output fields include:
- `symbol`
- `as_of_date`
- `current_price`
- `high_52w`
- `low_52w`
- `52w_return_pct`
- `dist_from_high_52w_pct`
- `error`

### 2. Tracked ticker universe expanded
Updated `data/tickers.csv` to include the full current holdings symbol set extracted from the Fidelity lots file.

This substantially improved merge coverage for the review engine.

### 3. Engine integration
Integrated the signal file into engine processing so output rows can carry:
- `CurrentPriceSignal`
- `High52W`
- `Low52W`
- `Return52WPct`
- `DistFromHigh52WPct`
- `Near52WeekHigh`

This is display/enrichment only and does not replace existing tax logic.

### 4. UI display patch
Updated `app.py` to expose key signal fields in the Streamlit tables.

Displayed fields include:
- `CurrentPriceSignal`
- `High52W`
- `DistFromHigh52WPct`
- `Near52WeekHigh`

Display behavior:
- rounded numeric formatting
- percentage formatting for distance from high
- Yes / No / — rendering for `Near52WeekHigh`
- graceful fallback when signal data is missing

### 5. Unsupported symbol maintenance
Implemented narrow updater maintenance for unsupported Finnhub symbols.

Behavior:
- detect unsupported-symbol style Finnhub failures, including 403 and “unsupported” / “not supported” response content
- normalize such errors to `finnhub_unsupported`
- preserve null signal fields for unsupported symbols
- preserve raw exception text for other error types

No engine logic or UI logic was changed as part of this maintenance step.

---

## Changed files

Core implementation files:
- `scripts/update_price_signals.py`
- `engine.py`
- `app.py`
- `config.yaml`
- `data/tickers.csv`
- `data/price_signals.csv`

Tests:
- `test_app_display.py`
- `test_update_price_signals.py`

Possible additional supporting files may also have changed during the phase depending on local implementation details; verify with Git history if needed.

---

## Key behavior now

### Cash-like handling
The engine can identify cash-like conversion opportunities and attach market-signal context where available.

Observed example:
- `GOVT` appeared in `cash_like_plan`
- signal fields were successfully populated
- the current action remained `convert_cash_like_to_fdlxx`

### Sell-plan handling
The signal layer is now available for future sell-candidate ranking and interpretation, even if a particular run does not need non-cash-like sales.

### Missing signal behavior
If a symbol is unsupported or unavailable in the signal source:
- the row still exists
- signal columns remain null
- display remains stable
- the updater records a normalized or raw error as appropriate

---

## Validation completed

### Updater / signal work
Validated signal generation locally after expanding the ticker set.

Observed output showed broad coverage across holdings and one unsupported symbol case (`FITLX`) that was later normalized in updater error handling.

### GitHub Actions
The GitHub-hosted daily signal workflow was run successfully.

This confirms the hosted refresh path is operational.

### UI validation
Focused display regression passed:
- `python -m pytest -q test_app_display.py`

The Streamlit page loaded locally and rendered the signal-enhanced tables successfully.

### Unsupported-symbol maintenance validation
Focused regression coverage passed:
- `python -m pytest -q test_update_price_signals.py test_app_display.py`

Validation confirmed:
- unsupported Finnhub-style responses classify as `finnhub_unsupported`
- generic exceptions still preserve raw text
- UI display regression remained green

---

## Preserved boundaries

These boundaries were intentionally preserved:
- no new market-data provider
- no broad historical price storage
- no hi/low/volume expansion beyond current simple need
- no engine decision-model redesign
- no UI redesign beyond adding signal columns
- no skip-list configuration added yet for unsupported symbols

This phase intentionally kept the system lightweight and operationally simple.

---

## Known limitations

- Some symbols may not be supported cleanly by Finnhub, such as certain mutual funds.
- Unsupported symbols currently remain in the ticker list and are recorded with null signal fields plus `finnhub_unsupported`.
- Signal data is currently informative/contextual; it is not yet used as a deep ranking model.
- The current design does not maintain full historical series.

---

## Recommended next phase

Recommended next phase: decide whether any further operational handling is needed for persistently unsupported symbols.

Preferred order:
1. First evaluate whether the current `finnhub_unsupported` labeling is already good enough.
2. Only if daily workflow noise becomes annoying, consider a tiny optional config-driven exclude/skip list.
3. Keep any next phase updater-only unless a stronger reason appears.

This should remain a narrow maintenance phase if pursued.

---

## Non-goals for the next phase

Unless explicitly approved, do not:
- add a second API provider
- redesign sell ranking around technical signals
- add historical candle storage
- add heavy analytics or charting
- broaden the app UI beyond small clarity improvements

---

## Resume instructions

At the start of the next session:
1. Point the assistant to the repository.
2. Provide `PROJECT_SCOPE.md`.
3. Provide this handoff file as the latest checkpoint.
4. Ask for the next narrow-phase recommendation and a ready-to-use Copilot prompt.

The default recommended continuation is:
- review whether unsupported-symbol handling is already sufficient
- if not, plan the smallest possible updater-only improvement

---

## Useful commands

### Run focused tests
```powershell
python -m pytest -q test_update_price_signals.py test_app_display.py
```

### Refresh signals locally
```powershell
python scripts/update_price_signals.py
```

### Run app
```powershell
streamlit run app.py
```

### Inspect Git status
```powershell
git status --short
```

---

## Summary of durable outcome

The repo now has a functioning lightweight market-signal layer that:
- refreshes daily in GitHub Actions
- enriches the engine output
- displays in the Streamlit UI
- handles unsupported Finnhub symbols more cleanly
- remains intentionally simple
