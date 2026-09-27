# Required market data and quantitative strategy stack

Implemented scope: Dukascopy, CFTC COT, CCXT (including Binance public derivatives),
Yahoo/yfinance intermarket proxies, ECB, TA-Lib, custom features, vectorbt, and
NautilusTrader. Existing MT5, Twelve Data, Coinbase, FRED and Forex Factory stay in place.
World Bank, Alpha Vantage, SEC EDGAR, OpenBB and Backtesting.py are not added.

## Setup

Use Python 3.12–3.14 and install the locked project dependencies (`uv sync --locked`).
The tested engine versions are vectorbt 0.28.5, NautilusTrader 1.228.0 and TA-Lib 0.6.8.
Plotly stays below 7 for vectorbt compatibility. CCXT 4.5.64 preserves compatibility
with the project's existing cryptography constraint.

Restart the API, worker and scheduler after updating. Set
`MATRADES_RESEARCH_DATA_ROOT` to persistent storage shared by API and worker.
The local Compose definition mounts the `research-data` volume for this purpose.
Storage has owner-specific raw, normalized, feature and experiment partitions.
Raw bytes and Parquet data are content-addressed, immutable and checksum-verified.
Adjacent imported windows are reused for the same owner, account, connection,
instrument, timeframe and configuration hash; first-seen overlapping prices win.

## Connections and account bindings

In Configuration → Connections, select the provider and supply its JSON configuration.
These public sources require no private exchange credentials. Configure each account's
Provider bindings, then use **Test & verify**. Do not infer a broker symbol from its
display name: map suffixes, contracts, and provider symbols explicitly.

Independent pair history must have `CANDLES` capability and `HISTORY` purpose for the
same account and lane. Context uses `REFERENCE`.
For CFTC choose `OPEN_INTEREST + REFERENCE`; for ECB/FRED choose account economic
context `MACROECONOMIC`; for Yahoo choose `CANDLES + REFERENCE`.
These sources cannot bind discovery, executable quote, contract terms or broker reconciliation.
Yahoo is a context proxy, not a replacement pair-history authority.

Examples (adapt keys to the actual selected broker instrument):

```json
{"symbol_map":{"EUR/USD":{"symbol":"EURUSD","price_scale":"100000"}}}
```

Dukascopy downloads public hourly LZMA `.bi5` tick partitions, validates the big-endian
records, preserves bid/ask data and aggregates midpoint OHLC with observed spread
statistics. Volume is **tick count**, not exchange volume or verified liquidity.
Candles with missing source-hour partitions are excluded rather than reconstructed.
Months in feed paths are zero-based. Verify `price_scale` for every instrument;
especially do not reuse an FX scale for gold, silver or index CFDs.

CCXT uses an explicit public exchange. For Binance derivatives choose `binanceusdm`:

```json
{"symbol_map":{"BTCUSD":{"symbol":"BTC/USDT:USDT"}}}
```

The contract suffix matters: spot BTC and a perpetual are different research markets,
and neither is automatically the broker's BTC CFD. Public capability checks govern
ticker, OHLCV, trades, books, funding and open-interest requests. Binance's non-unified
premium and basis endpoints are accessed directly; no duplicate order connector is
introduced. Funding/OI availability and historical retention remain exchange-limited.
Geographic restrictions, rate limits and missing symbols are reported, not bypassed.

CFTC requires an exact six-digit contract code, futures-only report type, and explicit
category fields from that report. Example for an FX financial futures reference:

```json
{"contracts":{"EUR/USD":{"code":"099741","report":"TFF","weeks":156,
"categories":{"leveraged_funds":["lev_money_positions_long","lev_money_positions_short"],
"asset_managers":["asset_mgr_positions_long","asset_mgr_positions_short"]}}}}
```

Supported datasets: LEGACY `6dca-aqww`, TFF `gpe5-46if`, DISAGGREGATED `72hh-3qpy`.
Confirm category fields for the chosen dataset. Positioning includes net, changes,
long/short ratio, rolling percentile, z-score, extremes and four-week momentum.
At least 13 observations are required for percentile/extreme features.
No report date is treated as its publication timestamp. Without an archived release
time, COT observations are first-seen-only and cannot be joined to earlier backtest bars.

Yahoo intermarket context:

```json
{"proxies":{"nasdaq":"^IXIC","volatility":"^VIX","dollar":"DX-Y.NYB"}}
```

Prices are unadjusted, corporate actions are retained, and daily availability is
conservatively after the daily bar. Correlations, beta, relative strength, divergence
and named proxy directions use backward availability joins with a maximum three-day
staleness tolerance. Proxy direction is not a universal risk-on/risk-off classification.
Yahoo data is third-party research context; check the provider's usage/licensing terms.

ECB SDMX reference and policy-rate examples:

```json
{"series":[{"flow":"EXR","key":"D.USD.EUR.SP00.A"},
{"flow":"FM","key":"D.U2.EUR.4F.KR.DFR.LEV"}]}
```

Additional monetary/credit/yield context can use configured SDMX flow/keys. FRED can
use `{"series":["DGS10","DGS2","FEDFUNDS"]}` and requests a vintage at the research
cutoff. Macro responses without verified historical publication times remain
first-seen-only; an observation date alone never establishes historical availability.
Context fetched after the discovery cutoff is archived but withheld from hypothesis
generation. Historical macro availability is not inferred to fill that gap.
Earlier first-seen archives can inform a later discovery cutoff, but only for the
same owner, account, instrument, connection and configuration hash.

## Connected research lifecycle

Completed market selection → verified independent HISTORY binding (if configured)
→ immutable dataset → discovery/outer-holdout split → discovery-only feature store
and context → strategy hypotheses plus seven family baselines → vectorbt sweeps
→ deterministic held-out screen → immutable strategy proposal → formal broker-source
backtest/OOS/walk-forward/sensitivity/Monte Carlo/cost stress → native Nautilus order
replay → forward paper testing → review/activation → current-regime selection → setup
and authoritative risk checks → Trade Plan.
An independent-history binding preserves the broker-selected research timeframe.
Post-research validation begins after the entire research candle closes.

Features are computed internally at **bar close**. TA-Lib supplies ATR, ADX, RSI,
EMA/SMA, MACD, Bollinger bands, stochastic, ROC, OBV, CCI, Williams %R and true range.
These named indicators are also supported in structured strategy conditions and use
the same definitions in vectorbt, formal/native replay, paper and setup evaluation.
Indicator warm-up NaNs cannot satisfy a rule.
Custom features include delayed confirmed swings, higher/lower pivots, structure
breaks, historical range distances, volatility ranks, efficiency/slope, DST-aware
running sessions, previous-day extremes, equal-high/low and sweep proxies, rejections
and source-specific volume anomalies. Unknown warm-up values remain unknown.

`MATRADES_QUANTITATIVE_RESEARCH_MAX_COMBINATIONS` bounds search (default 256, maximum
4096). Families receive equal budgets. The grid varies structure window, ATR stop
and reward ratio on up to 20,000 recent discovery bars at the unchanged timeframe;
the archive retains the full dataset and reports the exact searched interval.
Shared Wilder ATR is computed in one causal pass, avoiding repeated prefix scans.
Each hypothesis retains its regime/session rules. Parameters are
checked on discovery's chronological train/inner-validation partitions and selected
only from supported neighboring regions. Outer holdout is never used for optimization.
The selected windows and Wilder ATR parameters are evaluated identically by formal
backtesting, paper monitoring and setup detection. A fixed baseline remains available
when no robust parameter region exists; this does not imply profitable eligibility.

Nautilus validation uses native market, stop and limit orders, position lifecycle,
partial targets, spread/slippage and commissions. Required broker tick/currency/
quantity/contract terms must exist. New formal runs record an `event_driven_execution`
gate; a failed gate blocks paper promotion, activation and strategy selection.
Observed quote ticks can drive the adapter directly. The connected formal broker
pipeline currently supplies candles, so it explicitly models an adverse-first OHLC
path with configured spread, rather than claiming historical observed tick fills.
L1 depth/queue impact and swaps are not verified by this simulation. Simulated risk
is in quote currency and does not replace account-currency risk/conversion checks.

The existing performance database records pair/account/provider/timeframe/regime
evidence, OOS performance and rolling 30/60/100-trade forward degradation. No newly
added source or engine grants broker execution permission. Strategy automation still
uses the separately saved opt-in account policy; live activation/commands remain
subject to existing account permissions and approval boundaries.

## Historical import and evidence APIs

All routes require authentication and are owner-scoped:

The market-research page includes account-scoped history import controls and archived
parameter-grid inspection. Imports need a verified `CANDLES` binding with `HISTORY`
purpose (`REFERENCE` for Yahoo proxies).

- `POST /api/v1/research-data/imports`: account, connection, instrument, timeframe,
  `start_at`, `end_at`; import up to 31 days per job, four concurrent jobs per owner.
- `GET /api/v1/research-data/imports|datasets|features|contexts|experiments`:
  inspect durable jobs, dataset lineage, feature versions and quantitative experiments.
- `GET /api/v1/research-data/experiments/{id}/results`: inspect the actual parameter
  grid, train/inner-validation results and regime performance.

Imports survive redelivery; stale jobs are recovered by the scheduler. Standalone
imports build datasets and features, not executable strategies. Selected-pair research
automatically archives its own history/features and experiment results. Unavailable
context is visible and neutral, never silently fabricated or substituted.

Primary implementation references:
[Dukascopy binary format](https://www.dukascopy.com/wiki/en/development/data-export/),
[CFTC reports](https://publicreporting.cftc.gov/stories/s/r4w3-av2u),
[CCXT](https://github.com/ccxt/ccxt/wiki/Manual),
[ECB SDMX](https://data.ecb.europa.eu/help/api/data),
[yfinance](https://ranaroussi.github.io/yfinance/),
[TA-Lib](https://github.com/TA-Lib/ta-lib-python),
[vectorbt](https://vectorbt.dev/api/portfolio/base/),
[NautilusTrader](https://nautilustrader.io/docs/latest/concepts/backtesting/).
