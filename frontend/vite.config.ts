import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build the SPA directly into trezarr/web/static so FastAPI can serve it
// via StaticFiles(html=True) mounted as the last route (Pattern 6).
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../trezarr/web/static",
    emptyOutDir: true,
  },
});
