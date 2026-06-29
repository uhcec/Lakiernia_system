// Sim-only Vite config for the isolated black-box simulation (scripts/sim/).
//
// Identical to vite.config.ts except it serves on :5174 and proxies the API to the SIM backend on
// :8001 (a throwaway sandbox DB) instead of the owner's dev backend on :8000. This lets the persona
// agents drive a real frontend without touching the owner's running dev session or data.
//
// Proxy prefixes are derived from the base config so they never drift from it. Not committed-critical;
// it exists purely to point the same app at the sandbox backend. Run with:
//   node node_modules/vite/bin/vite.js --config vite.sim.config.ts
import { defineConfig, mergeConfig, type UserConfig } from "vite";
import base from "./vite.config";

const SIM_BACKEND = "http://127.0.0.1:8001";

const baseConfig = base as unknown as UserConfig;
const basePrefixes = Object.keys(baseConfig.server?.proxy ?? {});
const proxy = Object.fromEntries(basePrefixes.map((prefix) => [prefix, { target: SIM_BACKEND }]));

export default mergeConfig(
  baseConfig,
  defineConfig({
    server: {
      host: "127.0.0.1",
      port: 5174,
      proxy,
    },
  }),
);
