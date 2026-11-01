import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "./globals.css";

// Rendered per request so Next.js can put the middleware's CSP nonce on its scripts.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Support Portal",
  description: "Answers from our documentation, with their sources and how they were reached.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
