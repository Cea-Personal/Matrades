export default function Mt5BridgeGuidePage() {
  return (
    <main className="guide-page">
      <p className="eyebrow">TraderX deployment guide</p>
      <h1>MetaTrader 5 bridge</h1>
      <p className="lede">The bridge is a read-only Expert Advisor that runs inside MetaTrader 5 on macOS or Windows and pushes account evidence to TraderX. It has no listening port and cannot submit orders.</p>
      <ol>
        <li>Install MT5 and sign in with the broker-provided <strong>investor password</strong>.</li>
        <li>In Command Center, create an MT5 setup code and <a download href="/mt5-bridge/TraderXReadOnlyBridge.mq5">download the TraderX Read-only Bridge EA</a>.</li>
        <li>In MT5, select <strong>File → Open Data Folder</strong>, place the file in <code>MQL5/Experts</code>, open it in MetaEditor, and compile it.</li>
        <li>In <strong>Tools → Options → Expert Advisors</strong>, add your TraderX HTTPS origin to “Allow WebRequest for listed URL”. Keep Auto Trading disabled.</li>
        <li>Attach <strong>TraderXReadOnlyBridge</strong> to any chart. In its Inputs tab, enter the TraderX API URL, Agent ID, and one-time setup code shown in Command Center.</li>
        <li>Return to Command Center, refresh, test and discover the account, bind it, and verify account data.</li>
      </ol>
      <p>The investor password stays inside MT5. If MT5 is disconnected or reports that terminal, account, or Expert Advisor trading is allowed, TraderX rejects the data and stays in LOCKDOWN.</p>
      <p>For a real bridge connection, use a publicly trusted HTTPS TraderX domain. The local Docker address uses a development certificate; MT5 must trust that certificate within its Wine environment before it can send snapshots.</p>
    </main>
  );
}
