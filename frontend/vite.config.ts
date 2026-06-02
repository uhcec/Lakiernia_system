import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./tests/setup.ts",
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/audit": {
        target: "http://127.0.0.1:8000",
      },
      "/health": {
        target: "http://127.0.0.1:8000",
      },
      "/manager": {
        target: "http://127.0.0.1:8000",
      },
      "/paints": {
        target: "http://127.0.0.1:8000",
      },
      "/process": {
        target: "http://127.0.0.1:8000",
      },
      "/work-orders": {
        target: "http://127.0.0.1:8000",
      },
    },
  },
});