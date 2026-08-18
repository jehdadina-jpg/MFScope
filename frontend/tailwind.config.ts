import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── Modern dark surfaces with depth ───────────────────────────────
        background: {
          DEFAULT: "#0B0E14",   // rich dark blue-black
          subtle:  "#131720",   // cards with slight elevation
          muted:   "#1A1F2E",   // hover states
          elevated: "#1F2637",  // elevated cards
        },
        border: {
          DEFAULT: "#1F2533",   // subtle border
          strong:  "#2D3548",   // dividers
          accent:  "#3D4A6B",   // highlighted borders
        },
        // ── Text with better contrast ─────────────────────────────────────
        text: {
          primary:  "#F1F5F9",  // crisp white
          secondary:"#94A3B8",  // soft gray
          muted:    "#64748B",  // muted
          accent:   "#38BDF8",  // accent text
        },
        // ── Premium gradient colors ───────────────────────────────────────
        gradient: {
          from: "#6366F1",      // indigo
          via:  "#8B5CF6",      // purple
          to:   "#EC4899",      // pink
          gold: {
            from: "#F59E0B",    // amber
            to:   "#EF4444",    // red-orange
          },
          blue: {
            from: "#3B82F6",    // blue
            to:   "#8B5CF6",    // purple
          },
          green: {
            from: "#10B981",    // green
            to:   "#06B6D4",    // cyan
          },
        },
        // ── Conviction with more vibrant colors ────────────────────────────
        conviction: {
          "strong-buy": "#22C55E",  // vibrant green
          "buy":        "#84CC16",  // lime green
          "hold":       "#94A3B8",  // neutral gray
          "sell":       "#F97316",  // orange
          "strong-sell":"#EF4444",  // red
        },
        // ── Semantic colors (more saturated) ──────────────────────────────
        positive: "#22C55E",   // vibrant green
        negative: "#EF4444",   // vibrant red
        neutral:  "#94A3B8",   // gray
        success:  "#10B981",   // green
        warning:  "#F59E0B",   // amber
        danger:   "#EF4444",   // red
        // ── Accent colors for CTAs ────────────────────────────────────────
        accent: {
          DEFAULT: "#6366F1",   // indigo — primary
          hover:   "#818CF8",   // lighter indigo
          dim:     "#312E81",   // dark indigo
          bright:  "#A78BFA",   // bright purple
        },
        // ── Special effects ───────────────────────────────────────────────
        glow: {
          blue:   "rgba(99, 102, 241, 0.4)",
          purple: "rgba(139, 92, 246, 0.4)",
          green:  "rgba(34, 197, 94, 0.4)",
          gold:   "rgba(245, 158, 11, 0.4)",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
        display: ["Inter", "system-ui", "sans-serif"],
      },
      fontSize: {
        "2xs": ["0.65rem", { lineHeight: "1rem" }],
      },
      borderRadius: {
        card: "1rem",
        badge: "9999px",
        xl: "1.25rem",
        "2xl": "1.5rem",
      },
      boxShadow: {
        card: "0 4px 6px -1px rgb(0 0 0 / 0.3), 0 2px 4px -2px rgb(0 0 0 / 0.3)",
        "card-hover": "0 20px 25px -5px rgb(0 0 0 / 0.4), 0 8px 10px -6px rgb(0 0 0 / 0.4)",
        glow: "0 0 24px 4px rgba(99, 102, 241, 0.3)",
        "glow-strong": "0 0 32px 8px rgba(99, 102, 241, 0.4)",
        "glow-green": "0 0 24px 4px rgba(34, 197, 94, 0.3)",
        "glow-gold": "0 0 24px 4px rgba(245, 158, 11, 0.3)",
        inner: "inset 0 2px 4px 0 rgb(0 0 0 / 0.3)",
        xl: "0 20px 25px -5px rgb(0 0 0 / 0.5), 0 8px 10px -6px rgb(0 0 0 / 0.5)",
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "gradient-conic": "conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))",
        "gradient-shine": "linear-gradient(135deg, transparent 0%, rgba(255,255,255,0.1) 50%, transparent 100%)",
      },
      animation: {
        "pulse-soft": "pulse-soft 2.5s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in":    "fade-in 0.3s ease-out",
        "slide-up":   "slide-up 0.4s ease-out",
        "slide-down": "slide-down 0.4s ease-out",
        "scale-in":   "scale-in 0.2s ease-out",
        "shimmer":    "shimmer 2s linear infinite",
        "glow":       "glow 2s ease-in-out infinite alternate",
        "float":      "float 3s ease-in-out infinite",
        "gradient":   "gradient 8s ease infinite",
      },
      keyframes: {
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%":      { opacity: "0.7" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to:   { opacity: "1" },
        },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(16px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
        "slide-down": {
          from: { opacity: "0", transform: "translateY(-16px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.95)" },
          to:   { opacity: "1", transform: "scale(1)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        glow: {
          "0%": { boxShadow: "0 0 20px 2px rgba(99, 102, 241, 0.3)" },
          "100%": { boxShadow: "0 0 32px 8px rgba(99, 102, 241, 0.5)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-10px)" },
        },
        gradient: {
          "0%, 100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
      },
      backdropBlur: {
        xs: "2px",
      },
    },
  },
  plugins: [],
};

export default config;
