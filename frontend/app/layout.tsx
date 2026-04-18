import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GridGreen — Carbon-aware ML copilot",
  description:
    "Estimate the CO2 cost of your ML training script and find the cleanest time to run it.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gg-bg text-gg-text">{children}</body>
    </html>
  );
}
