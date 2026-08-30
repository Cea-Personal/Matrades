import type { Metadata } from "next";
import Link from "next/link";
import { AppProviders } from "@/lib/providers";
import { SessionMenu } from "@/components/SessionMenu";
import "./globals.css";

export const metadata: Metadata = { title: "Matrades", description: "Autonomous evidence-based trading operations" };

const links = [["/", "Overview"], ["/trading", "Trade desk"], ["/research", "Research"], ["/strategies", "Strategies"], ["/connections", "Connections"], ["/configuration", "Configuration"], ["/agents", "Agents"], ["/knowledge", "Knowledge"], ["/operations", "Operations"]] as const;
const extraFolders = [["market-research", "Market research"], ["strategy-research", "Strategy research"], ["trade-recommendations", "Trade recommendations"], ["generated-code", "Generated code"], ["mt5-bridge-ea", "MT5 bridge EA"]] as const;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><AppProviders><div className="shell"><aside className="sidebar"><Link className="brand" href="/">MATRADES</Link><p className="muted">Evidence, automation, and accountable execution.</p><nav className="nav" aria-label="Primary">{links.map(([href, label]) => <Link href={{ pathname: href }} key={href}>{label}</Link>)}<div className="nav-folder"><Link className="nav-folder-title" href={{ pathname: "/extras" }}>Extras</Link>{extraFolders.map(([folder, label]) => <Link className="nav-folder-link" href={{ pathname: "/extras", query: { folder } }} key={folder}>{label}</Link>)}</div></nav><SessionMenu /></aside><main className="main">{children}</main></div></AppProviders></body></html>;
}
