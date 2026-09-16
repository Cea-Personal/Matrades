"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { SessionMenu } from "./SessionMenu";

const links = [["/", "Overview"], ["/trading", "Trade desk"], ["/research", "Research"], ["/strategies", "Strategies"], ["/connections", "Connections"], ["/configuration", "Configuration"], ["/agents", "Agents"], ["/knowledge", "Knowledge"], ["/operations", "Operations"]] as const;
const folders = [["market-research", "Market research"], ["strategy-research", "Strategy research"], ["trade-recommendations", "Trade recommendations"], ["generated-code", "Generated code"], ["mt5-bridge-ea", "MT5 bridge EA"]] as const;

export function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  return <aside className={`sidebar${open ? " sidebar-open" : ""}`}>
    <div className="sidebar-heading">
      <Link className="brand" href="/">MATRADES</Link>
      <button className="sidebar-toggle" aria-label="Toggle navigation" aria-expanded={open} aria-controls="workspace-navigation" onClick={() => setOpen(!open)}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d={open ? "m6 6 12 12M6 18 18 6" : "M4 6h16M4 12h16M4 18h16"} /></svg>
      </button>
    </div>
    <p className="sidebar-description">Evidence, automation,<br />and accountable execution.</p>
    <div id="workspace-navigation" className="sidebar-content">
      <nav className="nav" aria-label="Primary">
        {links.map(([href, label]) => <Link href={href} key={href} aria-current={pathname === href ? "page" : undefined} onClick={() => setOpen(false)}>{label}</Link>)}
        <div className="nav-folder">
          <Link className="nav-folder-title" href="/extras" aria-current={pathname === "/extras" ? "page" : undefined} onClick={() => setOpen(false)}><span aria-hidden="true">⌁</span> Extras</Link>
          {folders.map(([folder, label]) => <Link className="nav-folder-link" href={{ pathname: "/extras", query: { folder } }} key={folder} onClick={() => setOpen(false)}>{label}</Link>)}
        </div>
      </nav>
      <SessionMenu />
    </div>
  </aside>;
}
