# MT5 bridge on macOS + Wine

Matrades authenticates every bridge request with HMAC-SHA256. The signed bytes are:

```text
<unix_timestamp>.<nonce>.<request_body>
```

The EA/adapter must send these headers on every request:

```text
X-Timestamp: <unix timestamp in seconds>
X-Nonce: <unique random value>
X-Signature: <hex HMAC-SHA256 using the shared secret>
```

The repository includes `MatradesMT5BridgeEA.mq5`. MT5's native socket API is outbound-only, so
the EA publishes signed account snapshots to `/ingest` and broker-native metal catalogues,
contract terms, quotes, and bounded H1 candles to `/market-data/ingest`. It polls
`/commands/poll`, executes only bounded authorized commands, and posts signed receipts to
`/commands/receipts`. The Python bridge keeps command identity and receipts idempotent; it is not
an arbitrary broker-command proxy.

## Configuration

1. In Matrades **Connections**, create an **MT5 Bridge** credential. Use **Generate secure
   secret**, copy it for the EA, and save it. The encrypted UI credential is the authoritative
   bridge secret; the bridge validates signatures through the internal API and does not need the
   EA secret in Docker environment variables.
2. Create an **MT5 Bridge** connection, select that credential, set the account reference to the
   broker login/account identifier, and use `http://host.docker.internal:8765` as the bridge URL
   when Matrades runs in Docker Desktop on macOS.
3. Compile `MatradesMT5BridgeEA.mq5` in MetaEditor and attach it to one chart in the logged-in
   MT5 terminal. Set:
   - `InpBridgeUrl`: `http://127.0.0.1:8765` when the Python bridge runs on the same Wine/macOS
     network, or the host IP visible from Wine;
   - `InpBridgeSecret`: the same secret stored in Matrades;
   - `InpMatradesAccountId`: the UUID of the Matrades trading account;
   - `InpAccountReference`: the broker login (optional validation only);
   - `InpMarketDataPublishSeconds`: how often broker metal data is refreshed (default 60);
   - `InpResearchCandleCount`: bounded H1 history per metal symbol (default 100).
4. In MT5, add the bridge URL (for example `http://127.0.0.1:8765`) to **Tools → Options →
   Expert Advisors → Allow WebRequest for listed URL**, enable **Algorithmic Trading** globally,
   and enable it for this EA. Keep the terminal and EA running. The EA publishes an
   account/equity/positions snapshot every `InpPublishSeconds` seconds, publishes the terminal's
   XAU/XAG/gold/silver CFD symbols on the market-data interval, and polls for authorized commands
   on the same timer. Enabling Algorithmic Trading is security-sensitive because it enables every
   attached EA; remove or disable any EA that must not trade first.
5. In Matrades, click **Test bridge**. A valid response must advertise:
   `accounts.read`, `positions.read`, `history.read`, `commands.poll`, `commands.receipt`, and
   `fresh: true`. After the first usable market snapshot it also advertises `market.discovery`,
   `instruments.read`, `quotes.read`, `candles.read`, and `contract_terms.read`.
6. In **Provider bindings**, bind the account's **METALS · CFD** lane to the MT5 Bridge using
   **DISCOVERY** (or another advertised market-data capability) and verify the binding. The
   research worker will then use the broker symbols and prices rather than a Twelve Data proxy.

`127.0.0.1:8765` from inside the API container points at the container itself, not macOS. Use
`host.docker.internal` for the host bridge. Do not expose port 8765 publicly; restrict it to the
local machine/firewall and use a private network or HTTPS for remote deployments.

Start the Python bridge before attaching the EA. With Docker Compose:

```bash
docker compose -f infra/compose/compose.yaml up -d mt5-bridge
```

Or run it directly while using the UI credential authority:

```bash
MATRADES_MT5_AUTHORITY_URL='http://127.0.0.1:8000/api/v1/internal/mt5/authenticate' \
MATRADES_MT5_AUTHORITY_TOKEN='same-internal-token-as-the-api' \
  uv run uvicorn bridges.mt5.app:app --host 0.0.0.0 --port 8765
```

`MATRADES_MT5_AUTHORITY_TOKEN` authenticates the bridge service to the API; it is infrastructure
configuration and is not the EA secret. Set the same long random authority token for the API and
bridge processes. A standalone bridge without `MATRADES_MT5_AUTHORITY_URL` retains the legacy
`MATRADES_MT5_BRIDGE_SECRET` fallback for isolated development only and is not UI-managed.

Before the EA publishes its first snapshot, the bridge reports `waiting_for_ea`/`fresh: false`.
This is expected; once the EA is running and the WebRequest URL is allowed, the health check
becomes fresh. The Python bridge is a protocol server, not a broker terminal, so it must remain
running alongside MT5.

If the MT5 Experts log reports `HTTP -1, error 4014`, Algorithmic Trading is disabled globally or
for the attached EA. Enable it only after reviewing every attached EA and the Matrades execution
permissions. The bridge suppresses repeated copies of the same error and logs when publishing
recovers.

For deployments behind a mutual-TLS reverse proxy, set
`MATRADES_MT5_CLIENT_CERT_FINGERPRINT` to the proxy-verified client certificate
fingerprint. The bridge then requires that fingerprint in addition to HMAC;
local Wine setups can leave it unset and use the shared secret plus loopback
firewall restrictions.
