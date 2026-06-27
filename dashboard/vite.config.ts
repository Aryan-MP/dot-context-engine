import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Built assets are served by the daemon at /ui; in dev, proxy API calls
// to the local daemon so the dashboard works on the vite dev server too.
export default defineConfig({
  base: "/ui/",
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/status": "http://127.0.0.1:7337",
      "/context": "http://127.0.0.1:7337",
      "/memory": "http://127.0.0.1:7337",
      "/graph": "http://127.0.0.1:7337",
      "/ask": "http://127.0.0.1:7337",
      "/sync": "http://127.0.0.1:7337"
    }
  }
});
