
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const target = process.env.PANDEMIC_SERVER ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/rooms": target,
      "/meta": target,
      "/ws": { target, ws: true },
    },
  },
  test: { environment: "node", include: ["src/**/*.test.{ts,tsx}"] },
});
