import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./tests/setup.ts",
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    // One entry per backend router prefix. KEEP IN SYNC with app/*/router.py — a missing prefix is
    // NOT proxied, so the browser gets Vite's HTML 404 (not JSON) and every call to that API fails
    // with a generic "nie udało się…" message (this is what happened to /foils). Current backend
    // prefixes: auth, audit, clients, employees, foils, health, manager, paints, process, shop-settings,
    // stations, work-orders.
    proxy: {
      "/auth": {
        target: "http://127.0.0.1:8000",
      },
      "/audit": {
        target: "http://127.0.0.1:8000",
      },
      "/clients": {
        target: "http://127.0.0.1:8000",
      },
      "/employees": {
        target: "http://127.0.0.1:8000",
      },
      "/foils": {
        target: "http://127.0.0.1:8000",
      },
      "/health": {
        target: "http://127.0.0.1:8000",
      },
      "/stations": {
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
      "/shop-settings": {
        target: "http://127.0.0.1:8000",
      },
      "/work-orders": {
        target: "http://127.0.0.1:8000",
      },
    },
  },
});
