import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#15202b",
        mist: "#eef3f7",
        steel: "#5f7183",
        line: "#d6e0e8",
        accent: "#0f766e",
        accentSoft: "#d9f3ef",
      },
      boxShadow: {
        panel: "0 18px 40px rgba(21, 32, 43, 0.08)",
      },
    },
  },
  plugins: [],
} satisfies Config;