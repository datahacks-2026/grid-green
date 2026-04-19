/** @type {import('next').NextConfig} */
// Use 127.0.0.1 (not "localhost") so Node hits IPv4; uvicorn --host 127.0.0.1 does not listen on ::1.
const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
