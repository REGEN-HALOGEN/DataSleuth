// Evaluated at deployment time. This value is a public backend origin.
const configuredOrigin = process.env.DATASLEUTH_API_ORIGIN;
const origin = URL.canParse(configuredOrigin ?? "")
  ? new URL(configuredOrigin)
  : null;

if (
  !origin ||
  origin.protocol !== "https:" ||
  configuredOrigin !== origin.origin
) {
  throw new Error(
    "Set DATASLEUTH_API_ORIGIN to the exact HTTPS Render origin.",
  );
}

export const config = {
  framework: "vite",
  installCommand: "npm ci",
  buildCommand: "npm run build",
  outputDirectory: "dist",
  rewrites: [
    {
      source: "/api/v1/:path*",
      destination: `${origin.origin}/api/v1/:path*`,
    },
    { source: "/((?!api(?:/|$)|assets(?:/|$)).*)", destination: "/index.html" },
  ],
  headers: [
    {
      source: "/api/v1/:path*",
      headers: [
        { key: "Cache-Control", value: "no-store" },
        { key: "Vercel-CDN-Cache-Control", value: "no-store" },
        { key: "x-vercel-enable-rewrite-caching", value: "0" },
      ],
    },
  ],
};
