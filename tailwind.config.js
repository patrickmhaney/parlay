/** Standalone Tailwind CLI -- no node_modules. `make css` after editing
 *  templates; the built CSS is committed. */
module.exports = {
  content: ["./app/templates/**/*.html", "./app/routers/**/*.py", "./app/deps.py"],
  theme: {
    extend: {
      colors: {
        bg:      "var(--bg)",
        surface: "var(--surface)",
        ink:     "var(--ink)",
        muted:   "var(--muted)",
        line:    "var(--line)",
        win:     "var(--win)",
        loss:    "var(--loss)",
        push:    "var(--push)",
      },
      fontFamily: {
        sans: ["Geist", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      fontSize: {
        xs:   ["0.75rem",  { lineHeight: "1rem" }],
        sm:   ["0.875rem", { lineHeight: "1.25rem" }],
        base: ["1rem",     { lineHeight: "1.5rem" }],
        lg:   ["1.25rem",  { lineHeight: "1.75rem" }],
        xl:   ["1.75rem",  { lineHeight: "2.125rem", letterSpacing: "-0.02em" }],
      },
      maxWidth: { app: "44rem" },
    },
  },
  plugins: [],
};
