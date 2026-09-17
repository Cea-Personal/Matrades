# MT5 bridge on macOS + Wine

When Matrades is running on the same host as Wine, it can start the configured MT5 terminal
automatically before issuing a new authenticated session. Set these environment variables to the
actual installation:

```bash
MATRADES_MT5_AUTO_START_ENABLED=true
MATRADES_MT5_WINE_BINARY=wine
MATRADES_MT5_WINEBOOT_BINARY=wineboot
MATRADES_MT5_WINE_PREFIX="$HOME/.wine-matrades"
MATRADES_MT5_TERMINAL_PATH="$HOME/.wine-matrades/drive_c/Program Files/MetaTrader 5/terminal64.exe"
MATRADES_MT5_STARTUP_TIMEOUT_SECONDS=30
```

The launcher uses argument arrays rather than a shell, initializes the Wine prefix when needed,
starts `terminal64.exe` if it is not already running, waits for the process to be alive, and only
then allows the MFA session endpoint to persist a session. If a configured terminal cannot start,
the endpoint returns `503` and does not create a session. An unset terminal path leaves the API
usable for non-desktop deployments.

For a cloud deployment, run this bridge process on the same VM/container host as Wine and MT5 and
configure the API to call its protected runtime controller:

```bash
MATRADES_MT5_RUNTIME_CONTROL_URL=https://mt5-runtime.example.com/runtime/start
MATRADES_MT5_RUNTIME_CONTROL_TOKEN=replace-with-a-long-random-runtime-token
```

Set the same runtime token on the cloud bridge, keep `/runtime/start` private behind the cloud
network or an HTTPS ingress, and configure the bridge host with its own `MATRADES_MT5_WINE_*` and
`MATRADES_MT5_TERMINAL_PATH` values. The API then requests startup remotely; it never tries to
launch Wine locally. Docker containers still cannot launch a separate host’s Wine process, so the
controller must run where the cloud Wine/MT5 installation exists.

## Railway runtime service

For the repository's Railway image, set the service Dockerfile path to `wine.Dockerfile`. The
image runs `start.sh`, which starts Xvfb, initializes the Wine prefix, installs MT5 when
`/app/mt5setup.exe` (or `MT5_INSTALLER_URL`) is available, starts `terminal64.exe`, and runs the
Matrades bridge on Railway's `$PORT`. Set these Railway variables on that service:

```bash
MATRADES_MT5_AUTO_START_ENABLED=true
MATRADES_MT5_RUNTIME_CONTROL_TOKEN=the-same-token-used-by-the-api
MATRADES_MT5_WINE_PREFIX=/opt/wineprefix
MATRADES_MT5_TERMINAL_PATH=/opt/wineprefix/drive_c/Program Files/MetaTrader 5/terminal64.exe
MT5_INSTALLER_PATH=/app/mt5setup.exe
```

Set `MATRADES_MT5_RUNTIME_CONTROL_URL` on the Matrades API service to the Railway public HTTPS
URL plus `/runtime/start`, for example
`https://your-mt5-service.up.railway.app/runtime/start`. Do not put the runtime token in the
browser or expose it through frontend configuration. Attach a Railway persistent volume at
`/opt/wineprefix` so MT5 installation, login state, and terminal configuration survive restarts.
If the installer is not copied into the repository, provide an approved `MT5_INSTALLER_URL` or
make the installer available at `MT5_INSTALLER_PATH`; otherwise the container exits with a clear
startup error.

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
