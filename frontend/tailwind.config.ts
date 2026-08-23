import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── Surfaces — a quiet, cool near-black, not pure black ──────────────
        canvas: "#0a0b0d",
        surface: {
          DEFAULT: "#111318",
          raised: "#161920",
          overlay: "#1c1f28",
          hover: "#20242e",
        },
        stroke: {
          DEFAULT: "rgba(255,255,255,0.07)",
          strong: "rgba(255,255,255,0.13)",
          accent: "rgba(124,138,255,0.35)",
        },
        ink: {
          DEFAULT: "#eef0f4",
          dim: "#a3a8b5",
          faint: "#686e7d",
        },
        // ── One accent, used with intent ─────────────────────────────────────
        brand: {
          DEFAULT: "#6d7bff",
          bright: "#8b96ff",
          dim: "#2b2f57",
          soft: "rgba(109,123,255,0.12)",
        },
        // ── Semantic — desaturated enough to sit next to data all day ────────
        up: { DEFAULT: "#3dd68c", soft: "rgba(61,214,140,0.12)" },
        down: { DEFAULT: "#f2637a", soft: "rgba(242,99,122,0.12)" },
        warn: { DEFAULT: "#e8a23d", soft: "rgba(232,162,61,0.12)" },
        // ── Conviction scale — one hue family, ramped by strength ────────────
        // Explicit "-soft" tokens rather than a bg-color/12 opacity modifier:
        // Tailwind's alpha-modifier resolution is unreliable for colors nested
        // two levels deep with multi-word keys, so the wash tone is its own
        // literal rgba() entry instead of relying on that syntax at render time.
        conviction: {
          "strong-buy": "#2fbf82",
          "strong-buy-soft": "rgba(47,191,130,0.12)",
          buy: "#7cc98f",
          "buy-soft": "rgba(124,201,143,0.12)",
          hold: "#8b90a0",
          "hold-soft": "rgba(139,144,160,0.12)",
          sell: "#e08a5c",
          "sell-soft": "rgba(224,138,92,0.12)",
          "strong-sell": "#e2596e",
          "strong-sell-soft": "rgba(226,89,110,0.12)",
        },
        // ── Riskometer — cool (safe) to hot (risky), six clean steps ─────────
        risk: {
          low: "#3dd68c",
          "low-soft": "rgba(61,214,140,0.12)",
          "low-moderate": "#8fd35f",
          "low-moderate-soft": "rgba(143,211,95,0.12)",
          moderate: "#e8c33d",
          "moderate-soft": "rgba(232,195,61,0.12)",
          "moderately-high": "#e8a23d",
          "moderately-high-soft": "rgba(232,162,61,0.12)",
          high: "#e8703d",
          "high-soft": "rgba(232,112,61,0.12)",
          "very-high": "#e2596e",
          "very-high-soft": "rgba(226,89,110,0.12)",
        },
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.01em" }],
      },
      borderRadius: {
        card: "0.875rem",
        pill: "9999px",
      },
      boxShadow: {
        card: "0 1px 2px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.04)",
        raised: "0 8px 24px -8px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.06)",
        ring: "0 0 0 2px rgba(109,123,255,0.45)",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.23, 1, 0.32, 1)",
        "in-out": "cubic-bezier(0.77, 0, 0.175, 1)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-300% 0" },
          "100%": { backgroundPosition: "300% 0" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.96)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
      },
      animation: {
        "fade-up": "fade-up 320ms cubic-bezier(0.23,1,0.32,1) both",
        "fade-in": "fade-in 200ms ease-out both",
        "scale-in": "scale-in 160ms cubic-bezier(0.23,1,0.32,1) both",
        shimmer: "shimmer 1.8s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
