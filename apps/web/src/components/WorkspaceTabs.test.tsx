import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { WorkspaceTabs } from "./WorkspaceTabs";

afterEach(cleanup);
const sections = [
  { id: "latest", label: "Latest", content: <label>Strategy idea<input defaultValue="" /></label> },
  { id: "history", label: "History", content: <p>Archived records</p> },
  { id: "settings", label: "Settings", content: <button>Save settings</button> },
];

test("shows one accessible panel and keeps unsaved inputs across switches", () => {
  render(<WorkspaceTabs label="Research workspace" sections={sections} />);
  expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
  expect(screen.getByRole("tabpanel")).toHaveAccessibleName("Latest");
  fireEvent.change(screen.getByRole("textbox", { name: "Strategy idea" }), { target: { value: "A pullback idea" } });
  fireEvent.click(screen.getByRole("tab", { name: "History" }));
  expect(screen.getByRole("tabpanel")).toHaveAccessibleName("History");
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Latest" }));
  expect(screen.getByRole("textbox")).toHaveValue("A pullback idea");
});

test("supports keyboard activation and roving focus", () => {
  render(<WorkspaceTabs label="Research workspace" sections={sections} />);
  const latest = screen.getByRole("tab", { name: "Latest" });
  latest.focus();
  fireEvent.keyDown(latest, { key: "ArrowLeft" });
  const settings = screen.getByRole("tab", { name: "Settings" });
  expect(settings).toHaveFocus();
  expect(settings).toHaveAttribute("aria-selected", "true");
  fireEvent.keyDown(settings, { key: "Home" });
  expect(latest).toHaveFocus();
  fireEvent.keyDown(latest, { key: "End" });
  expect(settings).toHaveFocus();
  fireEvent.keyDown(settings, { key: "ArrowRight" });
  expect(latest).toHaveFocus();
});

test("supports a controlled workflow and handles invalid selected sections", () => {
  const select = vi.fn();
  const view = render(<WorkspaceTabs label="Workflow" sections={sections} activeId="history" onSelect={select} />);
  fireEvent.click(screen.getByRole("tab", { name: "Settings" }));
  expect(select).toHaveBeenCalledWith("settings");
  view.rerender(<WorkspaceTabs label="Workflow" sections={sections} activeId="settings" onSelect={select} />);
  expect(screen.getByRole("tabpanel")).toHaveAccessibleName("Settings");
  view.rerender(<WorkspaceTabs label="Workflow" sections={sections} activeId="removed" />);
  expect(screen.getByRole("tabpanel")).toHaveAccessibleName("Latest");
});
