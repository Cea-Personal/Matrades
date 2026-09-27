"use client";

import { useId, useState, type ReactNode } from "react";

type ListProps<T> = {
  items: readonly T[]; children: (visible: T[]) => ReactNode; label: string; scopeKey?: string; pageSize?: number;
};

/** Client-side disclosure; source records are never discarded or mutated. */
export function ProgressiveList<T>(props: ListProps<T>) {
  return <ProgressivePage key={JSON.stringify([props.scopeKey ?? "default", props.pageSize ?? 3])} {...props} />;
}

function ProgressivePage<T>({ items, children, label, pageSize = 3 }: ListProps<T>) {
  const id = useId();
  const step = Math.max(1, pageSize);
  const [count, setCount] = useState(step);
  const visibleCount = Math.min(count, items.length);
  return <div className="progressive-list"><div id={id}>{children(items.slice(0, count))}</div>
    {items.length > step ? <div className="list-controls">
      <span className="muted" role="status">Showing {visibleCount} of {items.length} {label}</span>
      <div className="actions">
        {visibleCount < items.length ? <button type="button" className="btn compact" aria-controls={id} aria-label={`Load more ${label}`} onClick={() => setCount(count + step)}>Load more</button> : null}
        {visibleCount > step ? <button type="button" className="btn compact" aria-controls={id} aria-label={`Show fewer ${label}`} onClick={() => setCount(step)}>Show less</button> : null}
      </div>
    </div> : null}
  </div>;
}

export function newestFirst<T extends { created_at?: string; completed_at?: string; updated_at?: string | number }>(items: readonly T[]): T[] {
  const at = (item: T) => {
    const value = item.completed_at ?? item.created_at ?? item.updated_at;
    const timestamp = typeof value === "number" ? value : Date.parse(value ?? "");
    return Number.isFinite(timestamp) ? timestamp : 0;
  };
  return [...items].sort((left, right) => at(right) - at(left));
}
