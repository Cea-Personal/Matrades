"use client";

import { useId, useRef, useState, type ReactNode } from "react";

type WorkspaceSection = { id: string; label: string; content: ReactNode };

/** Keep panels mounted so switching sections cannot discard form drafts. */
export function WorkspaceTabs({ sections, label, activeId, onSelect }: { sections: WorkspaceSection[]; label: string; activeId?: string; onSelect?: (id: string) => void }) {
  const prefix = useId();
  const [selected, setSelected] = useState(sections[0]?.id);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const requested = activeId ?? selected;
  const active = sections.some(section => section.id === requested) ? requested : sections[0]?.id;
  const choose = (id: string) => { setSelected(id); onSelect?.(id); };
  return <div className="workspace-sections">
    <div role="tablist" aria-label={label} className="workspace-tabs">
      {sections.map((section, index) => <button key={section.id} type="button" role="tab"
        id={`${prefix}-tab-${section.id}`} aria-controls={`${prefix}-panel-${section.id}`}
        aria-selected={active === section.id} tabIndex={active === section.id ? 0 : -1}
        ref={element => { buttons.current[index] = element; }} onClick={() => choose(section.id)}
        onKeyDown={event => {
          const next = event.key === "ArrowRight" ? (index + 1) % sections.length
            : event.key === "ArrowLeft" ? (index - 1 + sections.length) % sections.length
              : event.key === "Home" ? 0 : event.key === "End" ? sections.length - 1 : null;
          if (next !== null) { event.preventDefault(); choose(sections[next].id); buttons.current[next]?.focus(); }
        }}>{section.label}</button>)}
    </div>
    {sections.map(section => <section key={section.id} id={`${prefix}-panel-${section.id}`}
      role="tabpanel" aria-labelledby={`${prefix}-tab-${section.id}`} hidden={active !== section.id}
      tabIndex={0} className="workspace-panel">{section.content}</section>)}
  </div>;
}
