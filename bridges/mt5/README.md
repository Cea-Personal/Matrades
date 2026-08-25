# MT5 read-only bridge on macOS + Wine

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
the EA publishes signed, read-only snapshots to the Python bridge's `/ingest` endpoint. The
Python bridge then serves `/health`, `/account`, `/positions`, `/history`, and `/snapshot` to
Matrades. No order placement, modification, or closing API is included.

## Configuration

1. In Matrades **Connections**, create an **MT5 Bridge** credential. Generate a long random
   secret and keep it private.
2. Create an **MT5 Bridge** connection, select that credential, set the account reference to the
   broker login/account identifier, and use `http://host.docker.internal:8765` as the bridge URL
   when Matrades runs in Docker Desktop on macOS.
3. Compile `MatradesMT5BridgeEA.mq5` in MetaEditor and attach it to one chart in the logged-in
   MT5 terminal. Set:
   - `InpBridgeUrl`: `http://127.0.0.1:8765` when the Python bridge runs on the same Wine/macOS
     network, or the host IP visible from Wine;
   - `InpBridgeSecret`: the same secret stored in Matrades;
   - `InpMatradesAccountId`: the UUID of the Matrades trading account;
   - `InpAccountReference`: the broker login (optional validation only).
4. In MT5, add the bridge URL (for example `http://127.0.0.1:8765`) to **Tools → Options →
   Expert Advisors → Allow WebRequest for listed URL**. Keep the terminal and EA running. The
   EA publishes an account/equity/positions snapshot every `InpPublishSeconds` seconds.
5. In Matrades, click **Test bridge**. A valid response must advertise:
   `accounts.read`, `positions.read`, `history.read`, `writes: false`, and `fresh: true`.

`127.0.0.1:8765` from inside the API container points at the container itself, not macOS. Use
`host.docker.internal` for the host bridge. Do not expose port 8765 publicly; restrict it to the
local machine/firewall and use a private network or HTTPS for remote deployments.

Start the Python bridge before attaching the EA. With Docker Compose:

```bash
docker compose -f infra/compose/compose.yaml up -d mt5-bridge
```

Or run it directly:

```bash
MATRADES_MT5_BRIDGE_SECRET='same-secret-as-matrades' \
  uv run uvicorn bridges.mt5.app:app --host 0.0.0.0 --port 8765
```

Before the EA publishes its first snapshot, the bridge reports `waiting_for_ea`/`fresh: false`.
This is expected; once the EA is running and the WebRequest URL is allowed, the health check
becomes fresh. The Python bridge is a protocol server, not a broker terminal, so it must remain
running alongside MT5.
