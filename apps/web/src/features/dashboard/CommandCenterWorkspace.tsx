"use client";

import { useState } from "react";

import { Integrations } from "@/features/integrations/Integrations";
import { Journal } from "@/features/journal/Journal";
import { JournalAnalytics } from "@/features/journal/JournalAnalytics";
import { ActiveMarkets } from "@/features/markets/ActiveMarkets";
import { InstrumentLibrary } from "@/features/markets/InstrumentLibrary";
import { InstrumentReactivation } from "@/features/markets/InstrumentReactivation";
import { MarketReplacement } from "@/features/markets/MarketReplacement";
import { MarketResearchReport } from "@/features/markets/MarketResearchReport";
import { Notifications } from "@/features/notifications/Notifications";
import { OpportunityBoard } from "@/features/opportunities/OpportunityBoard";
import { RecommendationPanel } from "@/features/opportunities/RecommendationPanel";
import { ApprovalReview } from "@/features/paper/ApprovalReview";
import { PaperTrading } from "@/features/paper/PaperTrading";
import type { AccountSummary } from "@/features/risk/AccountRiskSetup";
import { ResearchBacktest } from "@/features/strategies/ResearchBacktest";
import { StrategyBuilder } from "@/features/strategies/StrategyBuilder";
import { StrategyVersions } from "@/features/strategies/StrategyVersions";
import { ValidationReport } from "@/features/strategies/ValidationReport";
import { Jobs } from "@/features/system/Jobs";
import { SystemControl } from "@/features/system/SystemControl";
import { Positions } from "@/features/trades/Positions";
import { TradeMonitor } from "@/features/trades/TradeMonitor";

type Workspace =
  | "integrations"
  | "markets"
  | "strategies"
  | "paper"
  | "opportunities"
  | "monitoring"
  | "journal"
  | "operations";

const workspaces: Array<{ id: Workspace; label: string; description: string }> = [
  { id: "integrations", label: "Account connection", description: "Manage your MT5 read-only account connection." },
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
            onClick={() => setCurrent(workspace.id)}
            type="button"
          >
            {workspace.label}
          </button>
        ))}
      </nav>
      <div className="workspace-content">
        {current === "integrations" && (account ? <Integrations account={account} onAccountChanged={onAccountChanged} /> : <EmptyDataNotice area="Account connection" />)}
        {current === "markets" && <><EmptyDataNotice area="Market research" /><InstrumentLibrary /><MarketResearchReport /><ActiveMarkets /><MarketReplacement /><InstrumentReactivation /></>}
        {current === "strategies" && <><EmptyDataNotice area="Strategy research" /><StrategyBuilder /><StrategyVersions /><ResearchBacktest /><ValidationReport /></>}
        {current === "paper" && <><EmptyDataNotice area="Paper trading" /><PaperTrading /><ApprovalReview /></>}
        {current === "opportunities" && <><EmptyDataNotice area="Opportunity evaluation" /><OpportunityBoard /><RecommendationPanel /></>}
        {current === "monitoring" && <><EmptyDataNotice area="Position monitoring" /><Positions /><TradeMonitor /></>}
        {current === "journal" && <><EmptyDataNotice area="Trade journal" /><Journal /><JournalAnalytics /></>}
        {current === "operations" && <><EmptyDataNotice area="Operations" /><Jobs /><Notifications /><SystemControl /></>}
      </div>
    </section>
  );
}
