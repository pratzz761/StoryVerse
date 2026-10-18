import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const backend = path.resolve(__dirname, "../backend");
const python = path.join(backend, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
export default defineConfig({
  testDir: "./tests",
  testMatch: "**/*.spec.ts",
  timeout: 60000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:3001", trace: "retain-on-failure", screenshot: "only-on-failure", channel: process.env.PLAYWRIGHT_CHANNEL || (process.platform === "win32" ? "msedge" : "chromium") },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 1000 } } },
    { name: "mobile", use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" } }
  ],
  webServer: [
    { command: `"${python}" -m tests.run_browser_server`, cwd: backend, url: "http://127.0.0.1:8001/api/health", timeout: 30000, reuseExistingServer: !process.env.CI },
    { command: "node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3001", url: "http://127.0.0.1:3001", timeout: 60000, reuseExistingServer: !process.env.CI, env: { API_INTERNAL_URL: "http://127.0.0.1:8001", NEXT_PUBLIC_SUPABASE_URL: "", NEXT_PUBLIC_SUPABASE_ANON_KEY: "" } }
  ]
});
