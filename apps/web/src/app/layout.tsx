import type { Metadata } from "next";
import Link from "next/link";
import { AppProviders } from "@/lib/providers";
import { SessionMenu } from "@/components/SessionMenu";
import "./globals.css";

export const metadata: Metadata = { title: "Matrades", description: "Human-in-the-loop trading intelligence" };

const links = [["/", "Overview"], ["/trading", "Trade desk"], ["/research", "Research"], ["/strategies", "Strategies"], ["/connections", "Connections"], ["/configuration", "Configuration"], ["/agents", "Agents"], ["/knowledge", "Knowledge"], ["/operations", "Operations"]] as const;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><AppProviders><div className="shell"><aside className="sidebar"><Link className="brand" href="/">MATRADES</Link><p className="muted">Decisions with evidence. Execution by you.</p><nav className="nav" aria-label="Primary">{links.map(([href, label]) => <Link href={{ pathname: href }} key={href}>{label}</Link>)}</nav><SessionMenu /></aside><main className="main">{children}</main></div></AppProviders></body></html>;
}
