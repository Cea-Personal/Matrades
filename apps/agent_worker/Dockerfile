FROM python:3.13-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl \
    && curl -fsSL https://chatgpt.com/codex/install.sh | sh \
    && test -x /root/.local/bin/codex \
    && apt-get purge --yes --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:${PATH}"
WORKDIR /app

COPY . .
RUN echo "=== Current files inside /app ===" && find .

RUN pip install --no-cache-dir psycopg2-binary asyncpg && \
    pip install --no-cache-dir .
RUN codex --version
RUN mkdir -p /app/.codex 
RUN echo "$AUTH_JSON" > /app/.codex/auth.json

RUN chmod 755 /app/apps/agent_worker/entrypoint.sh
CMD ["/app/apps/agent_worker/entrypoint.sh"]
