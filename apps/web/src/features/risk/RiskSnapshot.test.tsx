import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { describe, expect, it } from "vitest";
import { RiskSnapshot } from "./RiskSnapshot";

describe("RiskSnapshot", () => {
  it("renders the authoritative pre-trade capacity evidence", () => {
    render(<RiskSnapshot snapshot={{ account_equity: "$189,000", starting_account: "$200,000", current_drawdown: "5.5%", maximum_allowed_drawdown: "8%", remaining_drawdown: "$5,000", daily_loss_remaining: "$2,900", existing_open_risk: "$1,200", candidate_trade_risk: "$500", portfolio_risk_after_trade: "$1,700", open_trades: 1, max_concurrent_trades: 2, additional_trade_capacity: 1 }}/>);
    expect(screen.getByText("$189,000")).toBeInTheDocument();
    expect(screen.getByText("Additional capacity")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });
});
