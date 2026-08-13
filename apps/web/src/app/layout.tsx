import Link from "next/link";
import { connection } from "next/server";
import { ReactNode } from "react";

import { Providers } from "./providers";
import "./globals.css";

export const metadata = { title: "TraderX", description: "Conservative trading decision support" };

export default async function RootLayout({ children }: { children: ReactNode }) {
  // CSP nonces are generated per request, so pages must not be statically rendered.
  await connection();

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
