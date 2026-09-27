import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { API_ROOT, ApiError, api, withStepUp } from "./api";

const fetchMock = vi.fn<typeof fetch>();
beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  window.sessionStorage.clear();
});
afterEach(() => { vi.unstubAllGlobals(); fetchMock.mockReset(); });

test.each([
  ['{"detail":"Agent timed out"}', "Agent timed out"],
  ['{"message":"Service unavailable"}', "Service unavailable"],
  ["upstream unavailable", "upstream unavailable"],
  ["<html>Gateway error</html>", "<html>Gateway error</html>"],
  ["", "Bad Gateway"],
  ['"quoted error"', "quoted error"],
])("returns an ApiError with usable detail for %s", async (body, detail) => {
  fetchMock.mockResolvedValue(new Response(body, { status: 502, statusText: "Bad Gateway" }));
  const error = await api("/test").catch((cause: unknown) => cause);
  expect(error).toBeInstanceOf(ApiError);
  expect(error).toMatchObject({ status: 502, detail, message: detail });
  expect(fetchMock).toHaveBeenCalledOnce();
});

test("preserves structured validation errors instead of losing their detail", async () => {
  const detail = [{ loc: ["body", "name"], msg: "Field required" }];
  fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 422 }));
  await expect(api("/test")).rejects.toMatchObject({ status: 422, detail });
});

test("handles empty successful responses without trying to parse JSON", async () => {
  fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
  await expect(api("/test", { method: "DELETE" })).resolves.toBeUndefined();
});

test("keeps cookie authentication, JSON headers, and stored step-up grants", async () => {
  window.sessionStorage.setItem("matrades_step_up", "stored-grant");
  fetchMock.mockResolvedValue(new Response('{"saved":true}', { status: 200 }));
  await expect(api("/test", { method: "POST", body: "{}" })).resolves.toEqual({ saved: true });
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toBe(`${API_ROOT}/test`);
  expect(options).toMatchObject({ credentials: "include", cache: "no-store", method: "POST" });
  const headers = new Headers(options?.headers);
  expect(headers.get("Content-Type")).toBe("application/json");
  expect(headers.get("Step-Up-Grant")).toBe("stored-grant");
});

test("does not replace multipart headers or explicit step-up grants", async () => {
  window.sessionStorage.setItem("matrades_step_up", "stored-grant");
  fetchMock.mockResolvedValue(new Response("{}"));
  await api("/test", { body: new FormData(), headers: { "Step-Up-Grant": "explicit-grant" } });
  const headers = new Headers(fetchMock.mock.calls[0][1]?.headers);
  expect(headers.has("Content-Type")).toBe(false);
  expect(headers.get("Step-Up-Grant")).toBe("explicit-grant");
});

test("step-up obtains a fresh scoped grant before running the sensitive action", async () => {
  window.sessionStorage.setItem("matrades_step_up", "stale-grant");
  fetchMock.mockResolvedValue(new Response('{"grant_id":"fresh-grant"}'));
  const action = vi.fn(async () => "saved");
  await expect(withStepUp("connection.change", "123456", action)).resolves.toBe("saved");
  expect(fetchMock.mock.calls[0][0]).toBe(`${API_ROOT}/auth/step-up`);
  const options = fetchMock.mock.calls[0][1];
  expect(new Headers(options?.headers).get("Step-Up-Grant")).toBe("");
  expect(JSON.parse(options?.body as string)).toEqual({ action_scope: "connection.change", code: "123456" });
  expect(action).toHaveBeenCalledWith("fresh-grant");
  expect(window.sessionStorage.getItem("matrades_step_up")).toBe("fresh-grant");
});

test("failed step-up never runs the sensitive action", async () => {
  fetchMock.mockResolvedValue(new Response('{"detail":"Invalid MFA code"}', { status: 401 }));
  const action = vi.fn();
  await expect(withStepUp("connection.change", "000000", action)).rejects.toBeInstanceOf(ApiError);
  expect(action).not.toHaveBeenCalled();
});
