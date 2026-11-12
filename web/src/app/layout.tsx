import type { Metadata } from "next";
import { headers } from "next/headers";
import type { ReactNode } from "react";
import { Providers } from "@/lib/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Deal Desk", template: "%s · Deal Desk" },
  description: "Brief to approved, costed proposal with a human in the loop. SAMPLE DATA ONLY.",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  // Reading the request headers makes every page dynamic, so each response gets a fresh CSP nonce.
  await headers();
  return (
    <html lang="en-GB">
      <body className="min-h-screen font-sans">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2"
        >
          Skip to content
        </a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
