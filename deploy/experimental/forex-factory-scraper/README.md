# ForexFactory scraper experiment

This optional sidecar runs the third-party
[ForexFactoryScrapper](https://github.com/AtaCanYmc/ForexFactoryScrapper) API on TraderX's
private Docker network. It is for local development and inspection only.

It is not an official economic-calendar source. Imported events are labelled
`SCRAPED_EXPERIMENTAL`, do not establish calendar coverage, and are excluded
from all recommendation and event-risk gates.

Start it only in a development environment:

```sh
TRADERX_ENABLE_EXPERIMENTAL_CALENDAR_SCRAPER=true \
docker compose -f deploy/compose.yaml --profile experimental-calendar-scraper up --build
```

The Compose profile passes that environment value only to its dedicated
experimental worker. If it is omitted or `false`, the worker rejects imports.

Then, as an MFA-verified owner, use **Markets → Experimental scraped calendar**.
Enter a start and end date (maximum 31 days), an optional comma-separated source
list (`forex`, `cryptocraft`, `energyexch`, `metalsmine`), plus `limit` and
`offset`. A blank source field means `forex`. TraderX calls the third-party
API's documented per-source, per-day route for every selected date; it does not
use an undocumented bulk endpoint. There is no production Compose service and a
production process refuses the experimental setting at startup.
