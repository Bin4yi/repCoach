import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RepCheck",
  description: "AI-drafted workout feedback for online coaches. The coach reviews everything.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // suppressHydrationWarning: browser extensions (e.g. Bitdefender adds bis_register / __processed_* attributes)
    // modify <html>/<body> before React hydrates. This only ignores attribute differences on these two tags.
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen antialiased" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
