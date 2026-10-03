import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import { nitro } from "nitro/vite";

// Render is opt-in. Keep local development and Wrangler preview unchanged.
const renderBuild = process.env["CHAI_DEPLOY_TARGET"] === "render";

export default defineConfig({
  plugins: [
    tailwindcss(),
    tanstackStart({
      server: { entry: "server" },
    }),
    nitro({
      preset: renderBuild ? "node-server" : "cloudflare-module",
      // Local Vite runs in Node; preview checks the built worker with Wrangler.
      devServer: { runner: "node-worker" },
      output: {
        dir: renderBuild ? "dist-render" : "dist",
        serverDir: renderBuild ? "dist-render/server" : "dist/server",
        publicDir: renderBuild ? "dist-render/public" : "dist/client",
      },
    }),
    react(),
  ],
  resolve: {
    tsconfigPaths: true,
    alias: { "@": `${process.cwd()}/src` },
    dedupe: [
      "react",
      "react-dom",
      "react/jsx-runtime",
      "react/jsx-dev-runtime",
      "@tanstack/react-query",
      "@tanstack/query-core",
    ],
  },
  optimizeDeps: {
    include: [
      "react",
      "react-dom",
      "react-dom/client",
      "react/jsx-runtime",
      "react/jsx-dev-runtime",
    ],
  },
  server: {
    port: 8080,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
