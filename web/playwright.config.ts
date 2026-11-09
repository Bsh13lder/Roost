import { defineConfig, devices } from "@playwright/test";

// M2 D7: while the live Roost gateway holds 18800, `make e2e` starts this
// throwaway, scripted gateway on 5173 instead (an allowed origin, roost/config.py).
const PORT = Number(process.env.ROOST_E2E_PORT ?? "18800");

// Ruling 4 (SDD ledger): written now, run later from Task 13's integration
// checkout once Task 11's turn loop exists for the scripted model to echo
// against. `webServer` starts the gateway itself so `npx playwright test`
// is a single command once that lands — see e2e/team.spec.ts for the flow.
//
// Task 9: `workers: 1` because chief.spec.ts runs serially against the
// single account the first spec to run creates (see helpers.ts), and a
// second worker process would race it for that same account. The
// per-bot script (team-script.json) rides along in the webServer's own
// env, right after ROOST_MODEL=scripted. C3: ROOST_FAKE_SCREEN=shop gives every Linux computer the "Fake shop"
// page (roost/desk/fake_shop.py) for e2e/computer-use.spec.ts.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
  },
  webServer: {
    command: `cd .. && ROOST_MODEL=scripted ROOST_MODEL_SCRIPT=web/e2e/fixtures/team-script.json ROOST_MODEL_CHECK_FILE=web/e2e/fixtures/models-page.html ROOST_SCHEDULER_TICK_SECONDS=2 ROOST_STEER_DEBOUNCE_SECONDS=0 ROOST_DESK=fake ROOST_VOICE=fake ROOST_FAKE_SCREEN=shop ROOST_FAKE_MAC_TREE=web/e2e/fixtures/mac-tree.json ROOST_MAC_HOME=$(mktemp -d) ROOST_DATA_DIR=$(mktemp -d) uv run uvicorn roost.gateway.app:create_app --factory --host 127.0.0.1 --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/auth/me`,
    reuseExistingServer: false,
    timeout: 30_000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
