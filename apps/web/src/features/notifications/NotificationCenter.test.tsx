import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { NotificationCenter } from "./NotificationCenter";

vi.mock("@/lib/api", () => ({ api: vi.fn(async (path: string) => path === "/operations/notifications" ? Array.from({ length: 7 }, (_, index) => ({ id: `notice-${index}`, title: `Notice ${index}`, body: "Recorded event", urgency: index === 6 ? "CRITICAL" : "NORMAL", read: index !== 6, created_at: `2026-09-${String(27 - index).padStart(2, "0")}T12:00:00Z` })) : path === "/operations/notifications/preferences" ? { in_app: true, browser_push: false, email: false, telegram: false, pushover: false, urgent_only_external: true } : []) }));
afterEach(cleanup);

test("makes older critical unread notifications discoverable without expanding the full inbox", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><NotificationCenter /></QueryClientProvider>);
  expect(await screen.findByText("1 unread · 1 urgent unread")).toBeInTheDocument();
  expect(screen.queryByText("Notice 6")).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: "Show notifications" }), { target: { value: "urgent" } });
  expect(screen.getByText("Notice 6")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Mark read" })).toBeEnabled();
  fireEvent.change(screen.getByRole("combobox", { name: "Show notifications" }), { target: { value: "unread" } });
  expect(screen.getByText("Notice 6")).toBeInTheDocument();
});
