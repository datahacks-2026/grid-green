import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        gg: {
          bg: "#0b1220",
          panel: "#0f172a",
          border: "#1f2937",
          accent: "#22c55e",
          accentDim: "#16a34a",
          warn: "#f59e0b",
          danger: "#ef4444",
          text: "#e2e8f0",
          muted: "#94a3b8",
        },
        ink: "#0b1220",
        leaf: "#22c55e",
        leafDeep: "#15803d",
        coal: "#1f2937",
        ash: "#94a3b8",
        cardBg: "#0f172a",
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "Inter", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
