import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Tauri geliştirme sunucusu sabit portu bekler (src-tauri/tauri.conf.json → devUrl).
// `--mode demo`: müşteri demosu için tek parça (dinamik içe aktarmalar gömülü) derleme.
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: "127.0.0.1",
    // Rust derlemesi (target/) ve Python ortamı (.venv) izlenmez: kilitli dosyalar Vite'ı çökertir.
    watch: { ignored: ["**/src-tauri/**", "**/engine/**"] },
  },
  build: {
    target: "es2022",
    outDir: mode === "demo" ? "dist-demo" : "dist",
    sourcemap: false,
    rollupOptions: mode === "demo" ? { output: { inlineDynamicImports: true } } : {},
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    css: false,
  },
}));
