import type { ReactNode } from "react";

export function Disclosure({ title, children, open = false }: { title: string; children: ReactNode; open?: boolean }) {
  return <details className="workspace-disclosure" open={open}>
    <summary>{title}</summary><div className="disclosure-content">{children}</div>
  </details>;
}
