// /v1 is proxied to the API (API_ORIGIN, read at build time), so the browser only ever talks to this origin.
//   API_ORIGIN=http://127.0.0.1:8000 npm run dev
import type { NextConfig } from "next";

const api = process.env.API_ORIGIN ?? (process.env.VERCEL ? undefined : "http://127.0.0.1:8000");
if (!api) throw new Error("set API_ORIGIN to the API's origin in the Vercel project settings");

const config: NextConfig = {
  compress: false, // gzip buffers the proxied event stream
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/v1/:path*", destination: `${api}/v1/:path*` }];
  },
  async headers() {
    return [{
      source: "/(.*)",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "Referrer-Policy", value: "no-referrer" },
      ],
    }];
  },
};

export default config;
