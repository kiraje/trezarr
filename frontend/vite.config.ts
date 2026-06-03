import path from "path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

// Build the SPA directly into trezarr/web/static so FastAPI can serve it
// via StaticFiles(html=True) mounted as the last route (Pattern 6).
// NOTE: Do NOT set `base` here — that would break FastAPI's absolute-path
// asset serving from the root mount. outDir and emptyOutDir are load-bearing.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    outDir: "../trezarr/web/static",
    emptyOutDir: true,
  },
})
