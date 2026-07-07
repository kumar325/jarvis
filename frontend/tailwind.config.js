/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        accent: "var(--accent)",
        "accent-dim": "var(--accent-dim)",
        panel: "var(--panel-bg)",
        "panel-border": "var(--panel-border)",
      },
      fontFamily: {
        mono: ["'Share Tech Mono'", "ui-monospace", "monospace"],
        condensed: ["'Rajdhani'", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 12px var(--accent-glow), 0 0 2px var(--accent-glow)",
      },
    },
  },
  plugins: [],
};
