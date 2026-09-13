import path from "node:path";

import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // Emits a self-contained server bundle, so the production image ships only
  // what the app actually needs rather than the whole node_modules tree.
  output: "standalone",
  // The repo is a pnpm workspace, so tracing must start above apps/web.
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),
  typescript: {
    // Type errors fail the build. `pnpm typecheck` runs the same check in CI.
    ignoreBuildErrors: false,
  },
  eslint: { ignoreDuringBuilds: false },
};

export default config;
