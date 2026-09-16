import type { Metadata } from "next";
import { AppProviders } from "@/lib/providers";
import { Sidebar } from "@/components/Sidebar";
import "./globals.css";

export const metadata: Metadata = { title: "Matrades", description: "Autonomous evidence-based trading operations" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><AppProviders><div className="shell"><Sidebar /><main className="main">{children}</main></div></AppProviders></body></html>;
}
