from __future__ import annotations

import re
from datetime import UTC, datetime

import httpx


class FredProvider:
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None) -> None:
        self.owns_client = client is None
        self.client, self.api_key = (
            client or httpx.AsyncClient(base_url="https://api.stlouisfed.org/fred", timeout=10),
            api_key,
        )

    async def series(self, series_id: str, *, as_of: datetime | None = None) -> dict:
        params = {"series_id": series_id, "api_key": self.api_key, "file_type": "json"}
        if as_of is not None:
            params.update(
                realtime_start=as_of.date().isoformat(), realtime_end=as_of.date().isoformat()
            )
        result = await self.client.get(
            "/series/observations",
            params=params,
        )
        result.raise_for_status()
        return result.json()

    async def close(self) -> None:
        if self.owns_client:
            await self.client.aclose()


class CftcProvider:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.owns_client = client is None
        self.client = client or httpx.AsyncClient(
            base_url="https://publicreporting.cftc.gov", timeout=10
        )

    async def cot(self, market: str, *, report: str = "LEGACY", weeks: int = 156) -> list[dict]:
        from adapters.market_data.public_research import COT_DATASETS

        if report not in COT_DATASETS or not re.fullmatch(r"[0-9]{6}", market):
            raise ValueError("COT requires a report type and exact six-digit CFTC contract code")
        if not 2 <= weeks <= 1040:
            raise ValueError("COT history must contain 2–1040 weeks")
        response = await self.client.get(
            f"/resource/{COT_DATASETS[report]}.json",
            params={
                "$limit": weeks,
                "$where": f"cftc_contract_market_code='{market}'",
                "$order": "report_date_as_yyyy_mm_dd DESC",
            },
        )
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            raise ValueError("CFTC returned no positioning for the exact contract")
        if any(str(row.get("cftc_contract_market_code")) != market for row in rows):
            raise ValueError("CFTC returned another contract's positioning")
        return sorted(rows, key=lambda row: row["report_date_as_yyyy_mm_dd"])

    async def close(self) -> None:
        if self.owns_client:
            await self.client.aclose()


def positioning_features(
    rows: list[dict],
    *,
    long_field: str,
    short_field: str,
    available_at: datetime | None = None,
    window: int = 52,
) -> list[dict]:
    """Rolling COT features; observation date is NEVER used as publication date.

    Without an archived release timestamp, first-seen time is conservative. These
    retrospectively fetched observations cannot be joined to earlier backtest bars.
    """
    from statistics import fmean, pstdev

    seen = available_at or datetime.now(UTC)
    if seen.tzinfo is None or window < 2:
        raise ValueError("aware availability timestamp and rolling window required")
    nets = []
    result = []
    dates = [row["report_date_as_yyyy_mm_dd"] for row in rows]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ValueError("COT observations must be unique and chronological")
    observed_dates = [
        datetime.fromisoformat(value.replace("Z", "+00:00")).date() for value in dates
    ]
    for index, row in enumerate(rows):
        long, short = int(row[long_field]), int(row[short_field])
        if long < 0 or short < 0:
            raise ValueError("negative COT positions")
        net = long - short
        history = [*nets[-(window - 1) :], net]
        percentile = (
            sum(value < net for value in history) + sum(value == net for value in history) / 2
        ) / len(history)
        deviation = pstdev(history)
        result.append(
            {
                "observed_at": row["report_date_as_yyyy_mm_dd"],
                "available_at": seen.isoformat(),
                "availability_basis": "FIRST_SEEN",
                "net": net,
                "weekly_change": net - nets[-1]
                if nets and (observed_dates[index] - observed_dates[index - 1]).days == 7
                else None,
                "long_short_ratio": long / short if short else None,
                "percentile": percentile if len(history) >= 13 else None,
                "z_score": (net - fmean(history)) / deviation
                if len(history) >= 13 and deviation
                else None,
                "extreme": (percentile <= 0.1 or percentile >= 0.9) if len(history) >= 13 else None,
                "momentum_4w": net - nets[-4]
                if len(nets) >= 4 and (observed_dates[index] - observed_dates[index - 4]).days == 28
                else None,
                "open_interest": row.get("open_interest_all"),
                "sample_count": len(history),
            }
        )
        nets.append(net)
    return result
