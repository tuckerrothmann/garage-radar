import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Porsche Guards Red accent
        radar: {
          red:    "#CC0000",
          dark:   "#111827",
          card:   "#1F2937",
          border: "#374151",
          muted:  "#6B7280",
        },
      },
    },
  },
  plugins: [],
};
export default config;
