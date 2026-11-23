/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API runs separately (uvicorn on :8000); the dev server forwards its routes, so the
// browser sees one origin and the SSE stream needs no CORS. VQA_API_URL overrides the target.
const api = process.env.VQA_API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  // two pages: the app (index.html) and the admin site (admin.html, served on admin.<domain>)
  build: {
    rollupOptions: { input: { main: "index.html", admin: "admin.html" } },
  },
  server: {
    port: 5173,
    proxy: {
      "/v1": { target: api, changeOrigin: true },
      "/health": { target: api, changeOrigin: true },
      "/metrics": { target: api, changeOrigin: true },
      "/version": { target: api, changeOrigin: true },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
