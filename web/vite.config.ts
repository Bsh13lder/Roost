import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev server proxies /api to the Roost gateway (contract: 127.0.0.1:18800).
// `ROOST_API_TARGET` (read from the shell env or a .env file) points it at a
// gateway on another port instead — e.g. a throwaway one for screenshots —
// without touching the real one. `ws: true` is required so the live-events
// WebSocket (`/api/events`) upgrades through the proxy instead of failing
// the handshake.
const DEFAULT_API_TARGET = "http://127.0.0.1:18800";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "ROOST_");
  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        "/api": {
          target: env.ROOST_API_TARGET || DEFAULT_API_TARGET,
          changeOrigin: true,
          ws: true,
        },
      },
    },
    build: {
      outDir: "dist",
      // noVNC (a lazy chunk, used as published) uses top-level await, which only the esnext target allows.
      target: "esnext",
    },
  };
});
