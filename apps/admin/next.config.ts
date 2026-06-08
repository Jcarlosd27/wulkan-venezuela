import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@wulkan/config", "@wulkan/domain", "@wulkan/shared", "@wulkan/ui"]
};

export default nextConfig;
