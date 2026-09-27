import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { ProgressiveList, newestFirst } from "./ProgressiveList";

afterEach(cleanup);
const items = Array.from({ length: 7 }, (_, index) => `Record ${index + 1}`);
function list(scopeKey = "account-a") {
  return <ProgressiveList items={items} label="research records" scopeKey={scopeKey}>{visible => <ul>{visible.map(item => <li key={item}>{item}</li>)}</ul>}</ProgressiveList>;
}

test("shows three records, reveals the rest in batches and can collapse again", () => {
  render(list());
  expect(screen.getAllByRole("listitem")).toHaveLength(3);
  expect(screen.getByRole("status")).toHaveTextContent("Showing 3 of 7");
  fireEvent.click(screen.getByRole("button", { name: "Load more research records" }));
  expect(screen.getAllByRole("listitem")).toHaveLength(6);
  fireEvent.click(screen.getByRole("button", { name: "Load more research records" }));
  expect(screen.getAllByRole("listitem")).toHaveLength(7);
  expect(screen.queryByRole("button", { name: "Load more research records" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show fewer research records" }));
  expect(screen.getAllByRole("listitem")).toHaveLength(3);
});

test("resets when the account or filter changes, including when returning to the first account", () => {
  const view = render(list());
  fireEvent.click(screen.getByRole("button", { name: "Load more research records" }));
  view.rerender(list("account-b"));
  expect(screen.getAllByRole("listitem")).toHaveLength(3);
  view.rerender(list("account-a"));
  expect(screen.getAllByRole("listitem")).toHaveLength(3);
});

test("has no unnecessary controls for a short or empty list", () => {
  render(<ProgressiveList items={[]} label="empty records">{visible => <p>{visible.length} records</p>}</ProgressiveList>);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

test("sorts by newest completion without mutating the source or rejecting missing dates", () => {
  const source = [{ id: "old", created_at: "2026-09-01" }, { id: "missing" }, { id: "new", completed_at: "2026-09-27", created_at: "2026-08-01" }];
  expect(newestFirst(source).map(item => item.id)).toEqual(["new", "old", "missing"]);
  expect(source.map(item => item.id)).toEqual(["old", "missing", "new"]);
});

test("keeps tables semantically valid with controls outside the table", () => {
  const { container } = render(<ProgressiveList items={items} label="table rows">{visible => <div className="table-wrap"><table><tbody>{visible.map(item => <tr key={item}><td>{item}</td></tr>)}</tbody></table></div>}</ProgressiveList>);
  expect(screen.getAllByRole("row")).toHaveLength(3);
  expect(container.querySelector("table button")).toBeNull();
  const button = screen.getByRole("button", { name: "Load more table rows" });
  expect(document.getElementById(button.getAttribute("aria-controls")!)).toContainElement(screen.getByRole("table"));
});
