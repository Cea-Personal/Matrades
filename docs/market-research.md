# Account-based market research

Research ranks instruments for strategy investigation; scores are neither win
probabilities nor permission to place orders. The daily schedule and provider
universes are unchanged.

## Eligibility

Before any agent call, each candidate must have at least 20 positive, finite
closes, a valid non-crossed quote, and recent price movement. Quote freshness is
limited to 15 minutes (with five minutes allowed for clock skew). When provider
candle timestamps exist, the latest candle must be within three candle periods.
Receipt time is explicitly identified when the provider quote timestamp is absent.
During weekly closure, forex/metals use the Friday 17:00 New York close as the
freshness reference until Sunday 17:00 New York (DST-aware). Stocks receive a
weekend-only allowance referenced to Friday 16:00 New York. Quote evidence must
be no older than three hours before that reference close; candles must be within
three candle periods (at least three hours). Older-session evidence still fails.
Crypto has no weekend allowance. Future timestamps fail separately from stale
timestamps. These are weekly-session defaults, not authoritative venue holiday or
daily-break calendars. Closed-session fingerprints are marked WEEKEND_CLOSED.
Verified spreads exceeding half the mean absolute candle-to-candle price change
exclude a candidate. Closed/stale feeds can therefore produce no eligible result.

## Deterministic score

| Criterion | Weight | Measurement |
| --- | --- | --- |
| Trend strength | 20% | Absolute net movement / total absolute movement over the last 20 changes |
| Range structure | 15% | Position within the last 20 closes' range, relative to trend direction |
| Volatility suitability | 20% | Recent absolute returns relative to the available-history baseline |
| Trading cost | 20% | Verified spread relative to mean absolute price movement |
| Timeframe agreement | 15% | Direction agreement between recent closes and four-bar sampled closes |
| Event suitability | 10% | One minus supplied event risk |

Unknown spread and event risk use a neutral contribution and are disclosed.
Raw volume is not scored: provider volumes are not comparable across markets.
Weights and thresholds are initial research heuristics, not empirically optimized
strategy parameters. Range structure uses closes, not OHLC support/resistance.
Four-bar sampling is a coarse-timeframe proxy, not an independent higher-timeframe
feed. Session calendars, economic-event ingestion and account holdings are not
inferred or fabricated. Broker execution validation remains downstream; MT5
discovery already excludes disabled instruments.

## Reviews and selection

Specialists and the critic receive measured fingerprints and limitations.
Per-review adjustments are bounded to 10 points, and cumulative AI adjustment is
bounded to 15 points from the deterministic score. Critic adjustments are applied
before the final ranking. A reassessment or invocation failure still blocks the
affected lane, not other lanes.

Successful lanes are processed from strongest to weakest. Repeated underlying
exposure incurs a 10-point penalty; each matching directional forex currency
exposure incurs five points, capped at 15 total. Each lane reselects its best
candidate after this penalty. This is a deterministic diversification preference,
not measured return correlation, position-risk management or a hard exclusion.
The overview continues to show up to four lane winners, and strategy research is
queued against the same persisted winners.

Every fingerprint saves the measured criteria, regime, quality and limitations.
Eligibility rejection reasons and source references are retained. Existing archived
research is unchanged; new cycles use the improved algorithm.

## Backtesting and closed-market safety

Formal backtesting resolves the version's original owner/account/selection and
verified provider binding. Forex supports Twelve Data or MT5; metals require MT5;
crypto requires Coinbase. It does not choose the first available connection or
silently switch providers. Existing versions resolve their original draft basis.
The worker rechecks the binding and pins MT5 history to the account. The current
MT5 adapter uses the EA's published candle snapshot, not arbitrary deep history;
only its published timeframe is supported. Requested windows may have fewer
candles available, and insufficient history fails validation. Future end dates
are clipped to the current time, with the requested end preserved for audit.

Last-session history can support research and historical backtests while closed,
but strategy setup generation returns MARKET_CLOSED without entry/stop/targets.
Trade Plan creation is blocked during the weekly closure. After reopening the
normal setup freshness checks apply; historical results do not authorize execution.
The EA's optional InpResearchForexSymbols controls a bounded forex list alongside
its metals snapshot. EA source changes require recompiling and attaching the new
EA in MT5; they cannot take effect merely by rebuilding the Python services.
