import type { NextConfig } from "next";

// SITE_BASE_PATH is set only when the site is served under a sub-path (e.g. GitHub Pages).
const basePath = process.env.SITE_BASE_PATH || undefined;

const nextConfig: NextConfig = {
  output: "export",
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
