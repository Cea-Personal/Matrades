import Link from "next/link";
import { ReactNode } from "react";

import { Providers } from "./providers";
import "./globals.css";

export const metadata = { title: "TraderX", description: "Conservative trading decision support" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <header className="site-header"><Link className="brand" href="/">TraderX</Link><nav aria-label="Primary navigation" /></header>
          <main>{children}</main>
        </Providers>
      </body>
    </html>
  );
}
