import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { deferred } from "@/test/deferred";
import { useKeyedMutation } from "./useKeyedMutation";

afterEach(cleanup);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient();
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

test("claims each key synchronously and releases only the request that settles", async () => {
  const first = deferred<string>();
  const second = deferred<string>();
  const mutationFn = vi.fn((key: string) => key === "first" ? first.promise : second.promise);
  const onSuccess = vi.fn();
  const onError = vi.fn();
  const { result } = renderHook(() => useKeyedMutation({ mutationFn, onSuccess, onError }), { wrapper });
  act(() => {
    expect(result.current.mutate("first")).toBe(true);
    expect(result.current.hasPending()).toBe(true);
    expect(result.current.mutate("first")).toBe(false);
    expect(result.current.mutate("second")).toBe(true);
  });
  await waitFor(() => expect(mutationFn).toHaveBeenCalledTimes(2));
  expect([...result.current.pendingKeys]).toEqual(["first", "second"]);
  await act(async () => second.resolve("second result"));
  await waitFor(() => expect([...result.current.pendingKeys]).toEqual(["first"]));
  expect(onSuccess.mock.calls[0].slice(0, 2)).toEqual(["second result", "second"]);
  const error = new Error("first failed");
  await act(async () => first.reject(error));
  await waitFor(() => expect(result.current.hasPending()).toBe(false));
  expect(onError.mock.calls[0].slice(0, 2)).toEqual([error, "first"]);
  expect(mutationFn).toHaveBeenCalledTimes(2);
  mutationFn.mockResolvedValue("retry result");
  act(() => { expect(result.current.mutate("first")).toBe(true); });
  await waitFor(() => expect(result.current.pendingKeys.size).toBe(0));
  expect(mutationFn).toHaveBeenCalledTimes(3);
});

test("keeps a key claimed while asynchronous success handling is still pending", async () => {
  const success = deferred<void>();
  const onSuccess = vi.fn(() => success.promise);
  const mutationFn = vi.fn(async () => "result");
  const { result } = renderHook(() => useKeyedMutation({ mutationFn, onSuccess }), { wrapper });
  act(() => { result.current.mutate("source"); });
  await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
  act(() => { expect(result.current.mutate("source")).toBe(false); });
  expect(result.current.pendingKeys.has("source")).toBe(true);
  await act(async () => success.resolve());
  await waitFor(() => expect(result.current.hasPending()).toBe(false));
  expect(mutationFn).toHaveBeenCalledOnce();
});

test("a synchronous request error cannot leave the key permanently busy", async () => {
  const onError = vi.fn();
  const mutationFn = vi.fn((): Promise<string> => { throw new Error("request failed"); });
  const { result } = renderHook(() => useKeyedMutation({ mutationFn, onError }), { wrapper });
  act(() => { result.current.mutate("source"); });
  await waitFor(() => expect(onError).toHaveBeenCalledOnce());
  await waitFor(() => expect(result.current.pendingKeys.size).toBe(0));
  expect(mutationFn).toHaveBeenCalledOnce();
});
