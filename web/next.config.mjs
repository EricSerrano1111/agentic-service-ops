// A static export: no server rendering, API routes or middleware (ADR-080).
// `trailingSlash` writes each page as `<page>/index.html`, which is what the gateway's static
// mount serves for `/<page>/`.
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
