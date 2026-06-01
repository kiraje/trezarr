/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // 07-UI-SPEC.md §Color — exact hex tokens
        // Usage: bg-surface, text-primary, etc. (semantic class names per Implementation Note 2)
        "bg-base": "#0f1117",
        "bg-surface": "#1a1d27",
        "bg-stripe": "#1e2130",
        border: "#2d3148",
        "text-primary": "#e2e6f0",
        "text-muted": "#6b7280",
        accent: "#3b82f6",
        destructive: "#ef4444",
      },
    },
  },
  plugins: [],
};
