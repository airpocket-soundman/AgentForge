import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In docker-compose, VITE_API_PROXY_TARGET points at the backend service.
// Running `npm run dev` on the host falls back to localhost:8080.
const apiTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8080";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // listen on 0.0.0.0 so the container port is reachable
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
    },
  },
});
