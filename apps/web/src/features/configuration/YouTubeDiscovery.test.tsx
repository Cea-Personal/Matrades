import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { api } from "@/lib/api";
import { YouTubeDiscovery } from "./YouTubeDiscovery";

vi.mock("@/lib/api", () => ({ api: vi.fn() }));

const defaultSchedule = {
  configured: false, enabled: false, run_at: "05:00", timezone: "UTC", weekdays: [],
  query: "trading strategy", limit: 5, languages: ["en"], category: "trading",
  next_run_at: null,
};

beforeEach(() => {
  vi.mocked(api).mockImplementation(async path =>
    path.endsWith("/schedule") ? defaultSchedule : [],
  );
});
afterEach(() => { cleanup(); vi.mocked(api).mockReset(); });

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><YouTubeDiscovery /></QueryClientProvider>);
}

test("an exhausted search explains that no new videos were found and offers no empty ingestion", async () => {
  const base = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation((path, options) => path.endsWith("/search")
    ? Promise.resolve({ run_id: "empty", state: "SEARCHED", query: "trading strategy", discovered: 0, videos: [] })
    : base(path, options),
  );
  show();
  fireEvent.click(screen.getByRole("button", { name: "1. Search trading videos" }));
  expect(await screen.findByText(/No new videos found within this search's page budget/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Fetch transcripts for these videos" })).not.toBeInTheDocument();
  expect(vi.mocked(api).mock.calls.some(([path]) => path.endsWith("/transcripts"))).toBe(false);
});

test("new search results are reviewed before transcripts are fetched for that exact run", async () => {
  const base = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation((path, options) => {
    if (path.endsWith("/search")) return Promise.resolve({
      run_id: "new-run", state: "SEARCHED", discovered: 1,
      videos: [{ video_id: "video_123", title: "EURUSD trend method", url: "https://youtu.be/video_123" }],
    });
    if (path.endsWith("/transcripts")) return Promise.resolve({ created: 1, skipped: 0, failed: [] });
    return base(path, options);
  });
  show();
  fireEvent.click(screen.getByRole("button", { name: "1. Search trading videos" }));
  expect(await screen.findByText(/SerpApi found 1 new videos/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "EURUSD trend method" })).toHaveAttribute("href", "https://youtu.be/video_123");
  expect(vi.mocked(api).mock.calls.some(([path]) => path.endsWith("/transcripts"))).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Fetch transcripts for these videos" }));
  await waitFor(() => expect(api).toHaveBeenCalledWith(
    "/knowledge/youtube/runs/new-run/transcripts", { method: "POST" },
  ));
  expect(await screen.findByText(/1 transcript\(s\) indexed/)).toBeInTheDocument();
});

test.each(["SEARCHED", "PARTIAL", "FAILED"])("saved %s runs can fetch or retry their transcripts", async state => {
  const base = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation((path, options) => {
    if (path.endsWith("/runs")) return Promise.resolve([{
      id: "saved-run", state, trigger: "MANUAL_SEARCH", query: "gold breakout",
      discovered_videos: [{ video_id: "video_123", title: "Gold", url: "https://youtu.be/video_123" }],
    }]);
    if (path.endsWith("/transcripts")) return Promise.resolve({ created: 1, skipped: 0, failed: [] });
    return base(path, options);
  });
  show();
  const name = state === "SEARCHED" ? "Fetch saved transcripts" : "Retry unavailable transcripts";
  fireEvent.click(await screen.findByRole("button", { name }));
  await waitFor(() => expect(api).toHaveBeenCalledWith(
    "/knowledge/youtube/runs/saved-run/transcripts", { method: "POST" },
  ));
  expect(vi.mocked(api).mock.calls.some(([path]) => path.endsWith("/search"))).toBe(false);
});

test("new schedules default to automatic query planning and save the selected mode", async () => {
  const base = vi.mocked(api).getMockImplementation()!;
  let saved: Record<string, unknown> | undefined;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path.endsWith("/schedule") && options?.method === "PUT") {
      saved = JSON.parse(options.body as string);
      return { ...saved, configured: true, next_run_at: null };
    }
    return base(path, options);
  });
  show();
  expect(await screen.findByRole("combobox", { name: "Scheduled query selection" })).toHaveValue("AUTO_MARKET");
  expect(screen.queryByRole("textbox", { name: "Scheduled query" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Save YouTube schedule" }));
  await waitFor(() => expect(saved?.query_mode).toBe("AUTO_MARKET"));
  expect(saved?.limit).toBe(5);
  expect(vi.mocked(api).mock.calls.some(([path]) => path.endsWith("/search"))).toBe(false);
});

test("a saved fixed schedule can switch to automatic and shows its next query preview", async () => {
  const base = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path.endsWith("/schedule") && options?.method === "PUT") {
      const saved = JSON.parse(options.body as string);
      return { ...saved, configured: true, next_run_at: null, query_preview: {
        mode: "AUTO_MARKET", query: "gold XAUUSD CFD trending market pullback strategy backtest",
        reason: "Rotate among the latest top pairs.",
      } };
    }
    if (path.endsWith("/schedule")) return {
      ...defaultSchedule, configured: true, query: "my old scheduled query",
      query_mode: "FIXED", enabled: true,
    };
    return base(path, options);
  });
  show();
  expect(await screen.findByText(/my old scheduled query/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Edit / replace schedule" }));
  expect(screen.getByRole("combobox", { name: "Scheduled query selection" })).toHaveValue("FIXED");
  fireEvent.change(screen.getByRole("combobox", { name: "Scheduled query selection" }), { target: { value: "AUTO_MARKET" } });
  fireEvent.click(screen.getByLabelText("Mon"));
  fireEvent.click(screen.getByRole("button", { name: "Replace YouTube schedule" }));
  expect(await screen.findByText("gold XAUUSD CFD trending market pullback strategy backtest")).toBeInTheDocument();
  expect(screen.getByText("Next scheduled query preview")).toBeInTheDocument();
});
