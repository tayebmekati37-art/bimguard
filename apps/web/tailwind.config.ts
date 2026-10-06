import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F6F7F8",
        ink: "#1B2430",
        steel: { DEFAULT: "#2F5D8A", dark: "#244A6F", light: "#E6EEF5" },
        line: "#D5DAE0",
        muted: "#5C6773",
        status: { ok: "#2E7D4F", warn: "#B7791F", stale: "#C2571A", critical: "#B3372F" },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
