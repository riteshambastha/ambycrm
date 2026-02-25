import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Hide the Next.js dev tools indicator (the "N" logo in the corner)
  devIndicators: false,
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "img.clerk.com" },
      { protocol: "https", hostname: "images.clerk.dev" },
    ],
  },
};

export default nextConfig;
