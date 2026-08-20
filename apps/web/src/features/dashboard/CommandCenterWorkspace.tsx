"use client";

import { useEffect, useState } from "react";

import { Integrations } from "@/features/integrations/Integrations";
import { JournalWorkspace } from "@/features/journal/JournalWorkspace";
import { MarketsWorkspace } from "@/features/markets/MarketsWorkspace";
import { Notifications } from "@/features/notifications/Notifications";
import { OpportunitiesWorkspace } from "@/features/opportunities/OpportunitiesWorkspace";
import { PaperWorkspace } from "@/features/paper/PaperWorkspace";
import { AccountRiskSetup, type AccountSummary } from "@/features/risk/AccountRiskSetup";
import { StrategiesWorkspace } from "@/features/strategies/StrategiesWorkspace";
import { Jobs } from "@/features/system/Jobs";
import { SystemControl } from "@/features/system/SystemControl";
import { MonitoringWorkspace } from "@/features/trades/MonitoringWorkspace";

type Workspace =
  | "integrations"
  | "account-risk"
  | "markets"
  | "strategies"
  | "paper"
  | "opportunities"
  | "monitoring"
  | "journal"
  | "operations";

const workspaces: Array<{ id: Workspace; label: string; description: string }> = [
  { id: "integrations", label: "Integrations", description: "Connect verified account data and manage reviewed market-data and advisory-model providers." },
  { id: "account-risk", label: "Account & risk", description: "Review account identity and deliberately version governed risk limits." },
  { id: "markets", label: "Markets", description: "Research and explicitly approve eligible active markets." },
  { id: "strategies", label: "Strategies", description: "Build, test, and validate immutable strategy evidence." },
  { id: "paper", label: "Paper trading", description: "Compare current-data simulation with historical evidence." },
  { id: "opportunities", label: "Opportunities", description: "Review risk-gated decision support, never automated orders." },
  { id: "monitoring", label: "Trade monitoring", description: "Track manually executed positions against frozen theses." },
  { id: "journal", label: "Journal", description: "Record outcomes and turn patterns into research hypotheses." },
  { id: "operations", label: "Operations", description: "Review jobs, notices, health, and redacted audit evidence." }
];

function EmptyDataNotice({ area }: { area: string }) {
  return <p className="workspace-notice"><strong>{area} is ready for governed data.</strong> No records have been created yet, so TraderX will not invent selections, strategy results, recommendations, positions, or audit conclusions.</p>;
}

export function CommandCenterWorkspace({
  account,
  onAccountChanged,
  startAtMarkets = false
}: {
  account: AccountSummary | null;
  onAccountChanged: () => Promise<void>;
  startAtMarkets?: boolean;
}) {
  const [current, setCurrent] = useState<Workspace>(startAtMarkets ? "markets" : "integrations");
  useEffect(() => {
    const openWorkspace = (event: Event) => {
      const requested = (event as CustomEvent<string>).detail;
      if (workspaces.some((item) => item.id === requested)) setCurrent(requested as Workspace);
    };
    window.addEventListener("traderx:workspace", openWorkspace);
    return () => window.removeEventListener("traderx:workspace", openWorkspace);
  }, []);
  const currentWorkspace = workspaces.find((workspace) => workspace.id === current)!;

  return (
    <section className="workspace-shell" id="traderx-workspace" aria-labelledby="workspace-heading" tabIndex={-1}>
      <header className="workspace-heading">
        <div>
          <p className="section-kicker">TraderX workspace</p>
          <h2 id="workspace-heading">{currentWorkspace.label}</h2>
          <p>{currentWorkspace.description}</p>
        </div>
      </header>
      <nav className="workspace-tabs" aria-label="TraderX workspaces">
        {workspaces.map((workspace) => (
          <button
            aria-pressed={current === workspace.id}
            className={current === workspace.id ? "active" : "secondary-button"}
            key={workspace.id}
            onClick={() => {
              setCurrent(workspace.id);
              window.history.replaceState(null, "", `/command-center?workspace=${workspace.id}`);
            }}
            type="button"
          >
            {workspace.label}
          </button>
        ))}
      </nav>
      <div className="workspace-content">
        {current === "integrations" && (account ? <Integrations account={account} onAccountChanged={onAccountChanged} /> : <EmptyDataNotice area="Integrations" />)}
        {current === "account-risk" && <AccountRiskSetup account={account} onAccountChanged={onAccountChanged} operational />}
        {current === "markets" && <MarketsWorkspace />}
        {current === "strategies" && <StrategiesWorkspace />}
        {current === "paper" && <PaperWorkspace />}
        {current === "opportunities" && <OpportunitiesWorkspace />}
        {current === "monitoring" && <MonitoringWorkspace />}
        {current === "journal" && <JournalWorkspace />}
        {current === "operations" && <div className="governed-workspace"><Jobs /><Notifications /><SystemControl /></div>}
      </div>
    </section>
  );
}
