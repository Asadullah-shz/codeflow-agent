import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        terminal: {
          bg: "#0d1117",
          text: "#c9d1d9",
          green: "#3fb950",
          red: "#f85149",
          yellow: "#d29922",
          blue: "#58a6ff",
          purple: "#bc8cff",
        },
      },
    },
  },
  plugins: [],
};
export default config;