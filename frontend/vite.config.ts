/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  // API_PROXY_TARGET lets the end-to-end tests point a second dev server at a separate test API.
  const env = loadEnv(mode, ".", "");
  return {
    plugins: [react()],
    server: {
      port: 5173,
      // The browser calls /api/... on the Vite server, which forwards it to FastAPI.
      // Same origin for the browser, so no CORS problems in development.
      proxy: { "/api": env.API_PROXY_TARGET || "http://127.0.0.1:8000" },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: "./src/test/setup.ts",
      include: ["src/**/*.test.{ts,tsx}"],     // e2e/*.spec.ts are run by Playwright, not Vitest
    },
  };
});
