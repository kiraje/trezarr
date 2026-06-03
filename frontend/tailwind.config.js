/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      colors: {
        // ── BRIDGE TOKENS — keep until ALL pages reskinned in Phase 15 ──
        // These five keys do NOT collide with shadcn's namespace.
        // They preserve existing page classes (bg-base, text-primary, etc.)
        // until Phase 15 removes them. (D-05)
        "bg-base":      "#0f1117",
        "bg-surface":   "#1a1d27",
        "bg-stripe":    "#1e2130",
        "text-primary": "#e2e6f0",
        "text-muted":   "#6b7280",

        // ── SHADCN CSS-VARIABLE TOKENS ──
        // Values in :root are bare H S% L% channel triples (no hsl() wrapper).
        // The hsl() wrapper is applied here in tailwind.config.js only.
        // Writing hsl() inside the CSS variable silently breaks bg-primary/50. (D-02)
        border:     "hsl(var(--border))",
        input:      "hsl(var(--input))",
        ring:       "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT:    "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT:    "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT:    "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT:    "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT:    "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT:    "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT:    "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Sidebar tokens — required by shadcn sidebar.tsx CSS variable references
        sidebar: {
          DEFAULT:                "hsl(var(--sidebar-background))",
          foreground:             "hsl(var(--sidebar-foreground))",
          primary:                "hsl(var(--sidebar-primary))",
          "primary-foreground":   "hsl(var(--sidebar-primary-foreground))",
          accent:                 "hsl(var(--sidebar-accent))",
          "accent-foreground":    "hsl(var(--sidebar-accent-foreground))",
          border:                 "hsl(var(--sidebar-border))",
          ring:                   "hsl(var(--sidebar-ring))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to:   { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to:   { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up":   "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
