/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // NEXT_PUBLIC_API_URL is injected at build time via the Docker ARG (see Dockerfile).
  // It must be the publicly-accessible URL of the backend API — i.e. the URL that
  // both the Next.js server AND the browser can reach.
  // Default: http://localhost:8000  (works for local dev without Docker)
};

module.exports = nextConfig;
