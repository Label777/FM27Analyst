import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Порт 1420 — стандартный для Tauri dev-сервера
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: { port: 1420, strictPort: true },
  build: { target: "es2021", outDir: "dist" },
});
