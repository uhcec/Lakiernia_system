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
        brand: {
          100: "#efe8ff",
          800: "#31215e",
          900: "#24124f",
          ink: "#1f2152",
          muted: "#6d7093",
          line: "#e7e3f4",
          soft: "#faf8ff",
          surface: "#f4efff",
          warm: "#ff9b35",
          "warm-strong": "#ff8818",
        },
        shell: "#f6f4fb",
      },
      boxShadow: {
        panel: "0 18px 40px rgba(21, 32, 43, 0.08)",
        brand: "0 18px 38px rgba(36, 18, 79, 0.22)",
        inner: "inset 0 1px 0 rgba(255, 255, 255, 0.7)",
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(135deg, #ff9b35 0%, #ff6b2c 42%, #31215e 100%)",
      },
    },
  },
  plugins: [],
} satisfies Config;