import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import path from "path"

const isTauri = process.env.TAURI_ENV_PLATFORM !== undefined

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    host: "localhost",
    hmr: isTauri
      ? { protocol: "ws", host: "localhost", port: 5174 }
      : undefined,
    proxy: isTauri
      ? undefined
      : {
          "/api": {
            target: process.env.API_URL || "http://localhost:8000",
            rewrite: (path) => path.replace(/^\/api/, ""),
          },
        },
  },
})
