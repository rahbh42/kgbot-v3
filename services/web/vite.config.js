import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build to root (/) because Traefik serves at /
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist" }
});
