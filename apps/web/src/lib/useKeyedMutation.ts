import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";

type KeyedMutationOptions<T> = {
  mutationFn: (key: string) => Promise<T>;
  onSuccess?: (data: T, key: string) => void | Promise<void>;
  onError?: (error: Error, key: string) => void | Promise<void>;
};

/** Run independent row actions concurrently, but never duplicate an active key. */
export function useKeyedMutation<T>(options: KeyedMutationOptions<T>) {
  const active = useRef(new Set<string>());
  const [pendingKeys, setPendingKeys] = useState<ReadonlySet<string>>(new Set());
  const mutation = useMutation<T, Error, string>({
    ...options,
    retry: false,
    onSettled: (_data, _error, key) => {
      active.current.delete(key);
      setPendingKeys(new Set(active.current));
    },
  });

  const mutate = (key: string): boolean => {
    // Claim before rendering the disabled button, including same-tick clicks.
    if (active.current.has(key)) return false;
    active.current.add(key);
    setPendingKeys(new Set(active.current));
    mutation.mutate(key);
    return true;
  };

  return { mutate, pendingKeys, hasPending: () => active.current.size > 0 };
}
