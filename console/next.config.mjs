/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'export',
  images: { unoptimized: true },
  trailingSlash: true,
  experimental: { workerThreads: false, cpus: 1 },
  // Next blocks dev resources from a host it was not started on, which leaves the page unhydrated when
  // it is opened as 127.0.0.1 instead of localhost. Both spellings are the same machine here.
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
  devIndicators: false,
};

export default nextConfig;
