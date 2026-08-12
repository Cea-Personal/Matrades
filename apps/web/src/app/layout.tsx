import Link from "next/link";
import { ReactNode } from "react";

import { Providers } from "./providers";

export const metadata = { title: "TraderX", description: "Conservative trading decision support" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <header><Link href="/">TraderX</Link><nav aria-label="Primary navigation" /></header>
          <main>{children}</main>
        </Providers>
      </body>
    </html>
  );
}
