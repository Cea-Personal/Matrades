# Development-only sidecar for https://github.com/AtaCanYmc/ForexFactoryScrapper.
# It is intentionally fetched only while an operator opts into the experimental
# Compose profile, and is never included by the production Compose file.
FROM python:3.12-slim

ARG FOREX_FACTORY_SCRAPER_REF=main

# Avoid installing Git in the short-lived experimental image.  The archive is
# fetched only when this explicitly opted-in profile is built. The upstream
# requirements file also contains pytest and pre-commit, so only API runtime
# dependencies are installed below.
RUN python -c "import sys, urllib.request, zipfile; ref = sys.argv[1]; urllib.request.urlretrieve(f'https://github.com/AtaCanYmc/ForexFactoryScrapper/archive/refs/heads/{ref}.zip', '/tmp/source.zip'); zipfile.ZipFile('/tmp/source.zip').extractall('/opt'); __import__('pathlib').Path('/opt/ForexFactoryScrapper-' + ref).rename('/opt/forex-factory-scraper')" "${FOREX_FACTORY_SCRAPER_REF}" \
    && rm /tmp/source.zip \
    && pip install --no-cache-dir \
      "Flask~=3.0.3" "Flask-Cors~=3.0.10" "forex-pytory==0.1.0" "python-dotenv~=1.0.0" \
    && useradd --system --uid 10001 scraper \
    && chown -R scraper:scraper /opt/forex-factory-scraper

WORKDIR /opt/forex-factory-scraper
USER 10001:10001
EXPOSE 5000
CMD ["python", "main.py"]
