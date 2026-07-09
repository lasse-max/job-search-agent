import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        chart: {
          page: "#0a141c",
          panel: "#0d1a24",
          card: "#13242f",
          ink: "#eef0ec",
          muted: "#9fb0b6",
          faint: "#6f828a",
          teal: "#57b6c4",
          tealDeep: "#1f6f7c",
          rust: "#e07a5c",
          gold: "#c7a86a",
          green: "#5bbf9a",
          warn: "#ec6c41"
        }
      },
      fontFamily: {
        serif: ["Newsreader", "Georgia", "serif"],
        sans: ["IBM Plex Sans", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"]
      }
    }
  },
  plugins: []
};

export default config;
