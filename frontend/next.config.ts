import type { NextConfig } from "next";

const deployed = process.env.VERCEL === "1" || process.env.STORYVERSE_PUBLIC_DEPLOYMENT === "true";
const api = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";
if (deployed) {
  const endpoint = new URL(api);
  if (endpoint.protocol !== "https:" || endpoint.username || endpoint.password || endpoint.search || endpoint.hash || endpoint.pathname !== "/" || ["localhost","127.0.0.1"].includes(endpoint.hostname)) throw new Error("Public deployment requires an HTTPS API_INTERNAL_URL origin");
  if (!process.env.NEXT_PUBLIC_SUPABASE_URL?.startsWith("https://") || !process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY) throw new Error("Public deployment requires the public Supabase URL and anon key");
  const publicKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (publicKey.startsWith("sb_secret_")) throw new Error("A Supabase secret key must never be public");
  if (publicKey.startsWith("eyJ")) {
    let role: string | undefined;
    try { role = JSON.parse(Buffer.from(publicKey.split(".")[1], "base64url").toString()).role; } catch {}
    if (role === "service_role") throw new Error("A Supabase service-role key must never be public");
  }
}

const config: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  experimental: { proxyTimeout: 360000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${api.replace(/\/$/, "")}/api/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "X-Frame-Options", value: "DENY" }
      ,...(deployed ? [{key:"Strict-Transport-Security",value:"max-age=31536000"},
        {key:"Content-Security-Policy",value:"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self' https:; media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; upgrade-insecure-requests"}] : [])
    ] }];
  }
};
export default config;
