import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { api } from "@/lib/api";
import AuthenticationPage from "./page";

vi.mock("@/lib/api", () => ({ api: vi.fn() }));
vi.mock("@/lib/providers", () => ({ useAuth: () => ({ refresh: vi.fn() }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

afterEach(() => {
  cleanup();
  vi.mocked(api).mockReset();
  window.history.replaceState(null, "", "/auth");
});

test("signup is unavailable after the installation has an owner", async () => {
  vi.mocked(api).mockResolvedValue({ signup_available: false });
  render(<AuthenticationPage />);
  await waitFor(() => expect(api).toHaveBeenCalledWith("/auth/registration-status"));
  expect(screen.queryByRole("button", { name: "Set up the owner account" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Continue to MFA" })).toBeInTheDocument();
});

test("first signup waits for an email link instead of showing a development token", async () => {
  vi.mocked(api).mockImplementation(async path => {
    if (path === "/auth/registration-status") return { signup_available: true };
    if (path === "/auth/signup") return { email_verified: false };
    throw new Error(`Unexpected endpoint ${path}`);
  });
  render(<AuthenticationPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Set up the owner account" }));
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "owner@example.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct-horse-battery" } });
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));
  expect(await screen.findByText(/Check your email for a verification link/)).toBeInTheDocument();
  expect(screen.queryByText(/development mode/i)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Resend verification email" })).toBeInTheDocument();
});

test("an email fragment verifies the address and opens MFA enrollment", async () => {
  window.history.replaceState(null, "", "/auth#verify=one-time-token");
  vi.mocked(api).mockImplementation(async path => {
    if (path === "/auth/registration-status") return { signup_available: false };
    if (path === "/auth/email-verifications") return { enrollment_token: "bootstrap" };
    if (path === "/auth/mfa/enrollments") return {
      enrollment_id: "enrollment", secret: "TOTPSECRET", setup_uri: "otpauth://totp/example",
      recovery_codes: ["one-time-recovery"],
    };
    throw new Error(`Unexpected endpoint ${path}`);
  });
  render(<AuthenticationPage />);
  expect(await screen.findByDisplayValue("one-time-token")).toBeInTheDocument();
  expect(window.location.hash).toBe("");
  fireEvent.click(screen.getByRole("button", { name: "Verify and enroll MFA" }));
  expect(await screen.findByText(/Save these recovery codes once/)).toBeInTheDocument();
  expect(vi.mocked(api).mock.calls).toContainEqual([
    "/auth/email-verifications", expect.objectContaining({ method: "POST" }),
  ]);
});
