// A static export: no server rendering, API routes or middleware (ADR-080).
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
