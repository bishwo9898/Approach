import type { Metadata } from "next";

import { AppProviders } from "@/components/app-providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Baseball Analytics",
  description: "Internal player analytics for the training facility.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
