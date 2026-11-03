import type { NextConfig } from "next";

// SITE_BASE_PATH is set only when the site is served under a sub-path (e.g. GitHub Pages).
const basePath = process.env.SITE_BASE_PATH || undefined;

const nextConfig: NextConfig = {
  output: "export",
  // Client code (the proof verifier) needs the base path to fetch files from this site.
  env: { NEXT_PUBLIC_BASE_PATH: basePath ?? "" },
  trailingSlash: true,
  basePath,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
