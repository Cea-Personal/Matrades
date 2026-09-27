# Strategy research, validation and monitoring

Research proposes reusable rules, not a current trade decision. Its initial
holdout screen is preliminary evidence, not formal validation or approval.
`NO_QUALIFYING_STRATEGY` means no hypothesis passed that screen; it does not mean
an activated strategy decided not to trade.

1. Accept a research proposal and create an immutable strategy version.
2. Run the formal backtest against the account/lane's verified historical-data
   binding. Backtest, out-of-sample, walk-forward, Monte Carlo, parameter sensitivity,
   doubled-cost stress and policy gates must pass for newly backtested price-rule versions.
3. Start a forward paper session from the strategy page. The worker observes new
   completed candles, records entry intents and simulates subsequent outcomes.
   Historical warmup cannot create past paper trades. Existing positions are not
   forcibly closed just because the available candle history ends.
4. Stop new paper entries when ready to finish, then wait for pending entries and
   open positions to resolve. Review recorded results. Approval requires at least
   ten closed trades, positive net P&L, gross profits at least gross losses, passing
   loss limits and complete observations. The API does not accept entered metrics.
5. Explicitly activate the approved version. Recurring monitoring produces current
   decisions and price levels separately from research. Suspension stops evaluation.
6. Create a Trade Plan only from an unexpired live signal. Account/broker risk checks
   still apply. Plan levels cannot override the validated signal, and plan expiry
   cannot extend its validity. This does not authorize or submit a broker order.

The API, Celery worker and Celery beat scheduler must all run the updated code.
Beat dispatches monitoring every minute. Provider history is cached until the next
completed candle is expected. No database migration is required: sessions and
monitoring use the existing resource store.

Starting a paper session also dispatches its first observation immediately. Beat
then provides recurring delivery. Queued backtests and backtests left running by a
lost worker are recovered automatically; a failed backtest returns the version to
validation with explicit failed gates instead of leaving it stuck in backtesting.
An unsuccessful paper run remains immutable evidence and returns the version to
validation so a new forward session can be started.

Paper trading is OHLC-based simulation, not broker demo-account execution. Entry
intents must be observed near the next bar's opening; fills use that bar's open
with the configured backtest costs. P&L is risk-normalized in simulated account
units, not broker lot units. Gaps invalidate paper evidence; provider downtime may
therefore require a new validation session. Loss limits currently use closed-trade
results, not intrabar mark-to-market equity. These results cannot guarantee live
performance.

Unsupported session/event rules block new signals. Supported high-impact event
blocking requires current calendar archive coverage. Stock-session handling uses
weekday New York hours, not a complete exchange holiday calendar. Legacy manual
paper approvals cannot activate: they need a new validated forward paper session.

## Optional autonomous validation

An owner can enable autonomous strategy validation per account in Configuration.
This is durable opt-in authorization for the non-executing stages only. For an
enabled account, the minute scheduler can accept a proposal that passed its hidden
holdout screen, create the immutable version, run a provider-pinned formal backtest,
start forward paper observation after every formal gate passes, stop entries when
the configured paper duration ends, and review the recorded paper gates.

The policy fixes the backtest lookback, costs, paper duration and maximum number of
paper attempts. Active hard `MAX_DAILY_LOSS` and `MAX_TOTAL_DRAWDOWN` constraints
are mandatory; missing authority blocks automation. A failed stage remains visible
and stops progression. Exhausting paper attempts returns control to the operator.
Disabling the policy prevents new autonomous transitions but does not erase evidence.

Approval after a passing paper review does not activate the strategy. Activation,
Trade Plan creation and broker execution remain explicit controls and continue to
use the live signal, risk authority, permissions and kill switches.

## CFD pair / regime research and selection

Each selected CFD instrument receives a deterministic, discovery-only pair profile
alongside the agent's three grounded hypotheses. The profile records bar-return
volatility, trend efficiency, reversal/autocorrelation proxies, session ranges and
volume proxies, and calendar coverage. Regimes have independent behaviour,
direction and relative-volatility axes. High-impact scheduled events within 30
minutes produce PRE_NEWS/POST_NEWS; absent coverage produces UNKNOWN, not NORMAL.
Event-aligned range comparisons are descriptive news-sensitivity proxies, not
causal forecasts. Execution costs are assumptions, not measured liquidity/slippage.

The fixed library adds LONG and SHORT baselines for trend following, momentum,
breakout, pullback, mean reversion, range trading and liquidity-sweep reversal.
The latter is explicitly an OHLC rejection proxy, not observed order flow. The
service tests all 14 baselines plus the three agent hypotheses without extra
agent calls. Positive family/direction alternatives become separate proposals;
each still needs its own immutable version, formal validation and forward paper
review. The primary proposal is a research ranking, not an optimality guarantee.

Regime alternatives are OR; dimensions in one colon-separated expression are AND:
`TRENDING:BULLISH:HIGH_VOLATILITY`. Unsupported labels or insufficient warmup
cannot generate entries. The same rules govern simulation, generated signal code
and current setup detection. Historical session/event restrictions are enforced
at entry; event-restricted strategies fail closed without covered calendar dates.
News-specific regimes (`PRE_NEWS`, `POST_NEWS`, `NORMAL_NEWS`) and the numeric
`news_regime` feature also require coverage. Forward observations freeze their
news context so a later calendar update cannot rewrite past entry decisions.

Formal validation uses chronological candle partitions and earlier-bar warmup,
not the last few trades of a whole-history run. Newly accepted research versions
pin their research selection cut: validation entries must be strictly after its
last completed candle. Reusing a holdout used to pick a hypothesis is not independent
validation. Newly researched versions require at least 60 completed, post-selection
candles before independent formal validation. Until then the run reports
WAITING_FOR_DATA, records its failed gates and an estimated next retry time.
Enabled autonomous-validation accounts retry at that time using current bindings,
policy costs and hard loss limits; disabling the policy stops these retries.
Manual accounts can rerun when enough history exists. This candle-depth floor is
not statistical proof. Genuine failed robustness checks do not auto-retry, and
future data is never invented to pass a gate.

Walk-forward checks use three fixed-rule forward folds (no train/refit optimizer).
Each partition needs at least two closed profitable-after-cost trades; this is a
screening floor, not statistical proof. Parameter sensitivity perturbs protection
by 0.8/1.2 and cost stress doubles spread, commission and slippage. Monte Carlo
bootstraps holdout R returns deterministically. Sharpe/Sortino are non-annualized
per-trade R ratios with a zero benchmark; undefined ratios remain unavailable.
Trade frequency is closed trades per elapsed calendar day, including market closures.

`GET /api/v1/strategies/library` exposes owner-scoped performance records pinned
to version/hash, account, instrument/listing/specification, provider connection
and timeframe. The Strategy page shows profiles, out-of-sample regime mapping,
robustness cuts, recent performance and rolling windows. Selection requires an
ACTIVE, formally and paper-validated version, at least ten positive-expectancy
out-of-sample trades in the exact current market regime, and at least ten recorded
positive forward trades. It ranks recent average R before historical average R.
No qualifying version means WAIT. The API rechecks this selection before making
a Trade Plan, then applies the existing live broker/risk checks. A selected strategy
still has to wait for its setup; it does not trade just because it was selected.

Activated versions keep a forward **shadow simulation** using validated paper
costs and limits. This is not a broker-fill performance feed. Complete rolling
30/60/100-trade windows with non-positive cost-adjusted R expectancy automatically
suspend the version and clear trade levels. Such a version cannot be reactivated
merely by clicking Activate; research and validate a revised version. Existing
evidence is retained, and no order is placed, closed or cancelled by suspension.

Current provider limitations still apply: MT5 snapshots expose a bounded history;
the research adapters do not supply a complete historical order book, measured
slippage or unrestricted multi-year candles. Sparse histories/regimes remain
ineligible. Older CFD versions need newly recorded robustness and per-regime
performance evidence before this selector can qualify them. No new SQL migration
is required; the performance database uses existing owner-scoped resources.
