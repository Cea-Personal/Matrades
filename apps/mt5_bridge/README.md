# TraderX-managed MT5 bridge

The standard MT5 bridge is an outbound, read-only MQL5 Expert Advisor. It runs inside the broker's
MetaTrader 5 terminal on macOS or Windows; it does not have a public URL and it never receives a
connection from TraderX. It can only submit terminal evidence to TraderX's fixed enrollment and
snapshot paths.

## First connection

1. In TraderX Command Center, choose **MetaTrader 5**, enter the account login and broker server,
   then select **Create MT5 setup code**.
2. Download `mql5/TraderXReadOnlyBridge.mq5`, or use the download shown in Command Center.
3. In MT5, select **File → Open Data Folder**, place the source in `MQL5/Experts`, open it with
   MetaEditor, and compile it.
4. In **Tools → Options → Expert Advisors**, add the TraderX HTTPS origin to **Allow WebRequest
   for listed URL**. For the local macOS/Wine setup, use `https://127.0.0.1:3000` rather than
   `localhost`; it is an HTTPS-only local endpoint. Keep Auto Trading disabled.
5. Attach `TraderXReadOnlyBridge` to any chart. In its inputs, paste the TraderX API URL, Agent ID,
   and one-time setup code. Do not attach it to a trading-enabled account.
6. Leave MT5 open. The EA sends a complete evidence snapshot every 15 seconds. Back in Command
   Center, select **Test & discover accounts**, bind the returned account, then choose **Verify
   account data**.

## Safety properties

- The EA uses only terminal/account information, positions, deals, symbols, and MQL5 `WebRequest`.
  It does not import or call an order function.
- MT5 must be connected with an investor password and report that terminal and account trading are
  disabled. TraderX does not treat the broker's general EA capability as an execution permission:
  this EA contains no order API. Otherwise no snapshot is sent.
- The one-time code expires after 24 hours. The EA stores its read-only agent credential only in
  MT5's sandboxed `MQL5/Files` directory. Remove the EA or renew its enrollment to revoke it.
- A missing or older-than-90-seconds snapshot is not accepted as account truth: TraderX remains in
  `LOCKDOWN`.

The previous Python/Windows bridge remains in this repository as a development reference only; the
Command Center no longer requires it.
