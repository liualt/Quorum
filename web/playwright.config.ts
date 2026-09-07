import { defineConfig, devices } from "@playwright/test";

/**
 * The browser end-to-end suite.
 *
 * Both halves of the app are started here, on ports of their own, against a
 * fresh temporary database: the golden flow asserts on stage transitions
 * and run counts, so it has to begin from an empty record every time. The two
 * test doubles the backend ships — the scripted model and the local executor —
 * are what make the run deterministic; nothing here exercises Agora, a real
 * model or an E2B sandbox (see README, "What is verified with test doubles").
 */

const BACKEND_PORT = 8010;
const WEB_PORT = 3010;
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`;
const WEB_URL = `http://localhost:${WEB_PORT}`;

/**
 * The backend's environment. `FOLLOW_UP_DELAY_SECONDS` is short so the test can
 * wait for the panel's proactive follow-up rather than sit out the six seconds
 * a real session uses.
 */
const BACKEND_ENV = {
  LLM_PROVIDER: "scripted",
  EXECUTOR: "local",
  SESSION_SECRET: "e2e",
  ALLOWED_ORIGINS: WEB_URL,
  FOLLOW_UP_DELAY_SECONDS: "2",
  CUSTOM_LLM_PUBLIC_BASE_URL: "",
  CUSTOM_LLM_AUTH_SECRET: "",
  AGORA_APP_ID: "",
  AGORA_APP_CERTIFICATE: "",
};

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? "line" : "list",
  timeout: 180_000,
  expect: { timeout: 20_000 },

  use: {
    baseURL: WEB_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },

  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],

  webServer: [
    {
      command: "uv run python ../scripts/e2e_server.py",
      cwd: "../server",
      url: `${BACKEND_URL}/api/health`,
      env: BACKEND_ENV,
      // Always start the backend that owns this test's temporary data.
      reuseExistingServer: false,
      timeout: 180_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: `npm run dev -- -p ${WEB_PORT}`,
      url: WEB_URL,
      env: { BACKEND_URL },
      reuseExistingServer: false,
      // Next's first compile of a cold `.next` is the slow part, not the server.
      timeout: 180_000,
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
