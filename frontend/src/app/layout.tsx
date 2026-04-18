import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GridGreen — Carbon-aware ML copilot",
  description: "Every model.fit() is a climate decision.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
