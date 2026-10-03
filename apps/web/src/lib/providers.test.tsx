import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { SessionMenu } from "@/components/SessionMenu";
import { api } from "./api";
import { AppProviders } from "./providers";

const navigation = vi.hoisted(() => ({ replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => navigation,
}));
vi.mock("./api", () => ({ api: vi.fn(), API_ROOT: "https://api.example/api/v1" }));

class FakeEventSource {
  addEventListener() {}
  removeEventListener() {}
  close() {}
}

const user = {
  id: "owner", owner_id: "owner", email: "owner@example.com", role: "OWNER",
  email_verified: false, email_verification_required: false, mfa_enabled: true,
};

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.mocked(api).mockReset();
  navigation.replace.mockReset();
});

test("sign-out removes the cached identity and returns to auth", async () => {
  vi.mocked(api).mockResolvedValueOnce(user).mockResolvedValueOnce(undefined);
  window.sessionStorage.setItem("matrades_step_up", "old-grant");
  render(<AppProviders><SessionMenu /></AppProviders>);
  fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));
  await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/auth"));
  expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
  expect(window.sessionStorage.getItem("matrades_step_up")).toBeNull();
  expect(vi.mocked(api).mock.calls).toContainEqual([
    "/auth/sessions", expect.objectContaining({ method: "DELETE" }),
  ]);
});

test("failed server sign-out stays signed in and displays an error", async () => {
  vi.mocked(api).mockResolvedValueOnce(user).mockRejectedValueOnce(new Error("unavailable"));
  render(<AppProviders><SessionMenu /></AppProviders>);
  fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Sign-out failed");
  expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  expect(navigation.replace).not.toHaveBeenCalled();
});
