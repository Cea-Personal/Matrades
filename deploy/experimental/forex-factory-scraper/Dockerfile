# Development-only sidecar for https://github.com/AtaCanYmc/ForexFactoryScrapper.
# It is intentionally fetched only while an operator opts into the experimental
# Compose profile, and is never included by the production Compose file.
FROM python:3.12-slim

ARG FOREX_FACTORY_SCRAPER_REF=main

RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --depth 1 --branch "${FOREX_FACTORY_SCRAPER_REF}" \
      https://github.com/AtaCanYmc/ForexFactoryScrapper.git /opt/forex-factory-scraper \
    && pip install --no-cache-dir -r /opt/forex-factory-scraper/requirements.txt \
    && useradd --system --uid 10001 scraper \
    && chown -R scraper:scraper /opt/forex-factory-scraper

WORKDIR /opt/forex-factory-scraper
USER 10001:10001
EXPOSE 5000
CMD ["python", "main.py"]
