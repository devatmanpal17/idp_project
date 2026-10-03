import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

// Explicitly override a developer's localhost API URL without editing .env files.
const build = spawnSync(
  process.execPath,
  [
    fileURLToPath(new URL("../node_modules/vite/bin/vite.js", import.meta.url)),
    "build",
    "--mode",
    "render",
  ],
  {
    stdio: "inherit",
    env: {
      ...process.env,
      CHAI_DEPLOY_TARGET: "render",
      VITE_DEPLOY_TARGET: "render",
      VITE_API_BASE_URL: "/api",
    },
  },
);
if (build.error) throw build.error;
process.exit(build.status ?? 1);
