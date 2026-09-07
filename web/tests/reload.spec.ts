import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * Reload and race paths the golden flow does not cover.
 *
 * 1. The session clock survives a reload: banked pauses stay subtracted and an
 *    open pause stays open (audit A14).
 * 2. A save whose response lands after a newer edit leaves that edit unsaved,
 *    and a run always uses the snapshot the panel shows as saved (audit A10).
 * 3. A reload while the interview is finishing lands on the assessment once
 *    it exists (audit A10).
 *
 * Same servers and test doubles as `e2e.spec.ts`; see `playwright.config.ts`.
 */

const CANDIDATE_NAME = "Reload candidate";

const CONSENT_TEXT =
  "I understand that AI interviewers will question me and that my speech and code will be processed to produce an assessment";

/** A `Panel` by its heading — the app's card surface has no landmark role. */
function panel(page: Page, heading: string): Locator {
  return page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: heading, exact: true }) });
}

/** As much of Monaco's global as the editing helpers touch. */
interface MonacoGlobal {
  editor: {
    getModels(): Array<{ uri: { path: string }; getValue(): string; setValue(value: string): void }>;
  };
}

async function openFile(page: Page, fileName: string) {
  await page.getByRole("tab", { name: new RegExp(`^${fileName.replace(".", "\\.")}`) }).click();
  await page.waitForFunction(
    (name) => {
      const models = (window as { monaco?: MonacoGlobal }).monaco?.editor.getModels();
      return Boolean(models?.some((model) => model.uri.path.endsWith(name)));
    },
    fileName,
    { timeout: 90_000 },
  );
}

/**
 * Append a line to one editable file through Monaco's own model, so the
 * workspace sees the change exactly as it would from typing (see
 * `replaceFile` in `e2e.spec.ts` for why not the keyboard).
 */
async function appendToFile(page: Page, fileName: string, line: string): Promise<string> {
  await openFile(page, fileName);
  return page.evaluate(
    ({ name, text }) => {
      const models = (window as { monaco?: MonacoGlobal }).monaco!.editor.getModels();
      const model = models.find((item) => item.uri.path.endsWith(name))!;
      const next = `${model.getValue()}\n${text}\n`;
      model.setValue(next);
      return next;
    },
    { name: fileName, text: line },
  );
}

interface SaveResponse {
  snapshot_id: string;
  content_hash: string;
}

/** Click Save and return what the server answered. */
async function saveAndCapture(page: Page): Promise<SaveResponse> {
  const [response] = await Promise.all([
    page.waitForResponse(
      (item) => item.request().method() === "PUT" && /\/api\/interviews\/[^/]+\/files$/.test(item.url()),
    ),
    panel(page, "Save and run").getByRole("button", { name: "Save", exact: true }).click(),
  ]);
  expect(response.ok()).toBe(true);
  return (await response.json()) as SaveResponse;
}

/** Consent, create, enter the workspace in text mode; returns the interview id. */
async function createAndEnter(page: Page): Promise<string> {
  await page.goto("/");
  await page.getByLabel("Display name or pseudonym").fill(CANDIDATE_NAME);
  await page.getByLabel(CONSENT_TEXT).check();
  await page.getByRole("button", { name: "Create interview" }).click();
  await page.getByRole("link", { name: "Enter workspace" }).click();
  await expect(page).toHaveURL(/\/interview\/itv_[0-9a-f]+$/);
  const id = page.url().split("/").pop()!;
  await enterWorkspace(page);
  return id;
}

/** From the pre-join screen to the live workspace. */
async function enterWorkspace(page: Page) {
  await page.getByRole("button", { name: "Continue with text" }).click();
  await expect(page.getByRole("heading", { name: "Save and run" })).toBeVisible({
    timeout: 60_000,
  });
}

function timer(page: Page): Locator {
  return page.getByRole("timer", { name: "Session time" });
}

/** The chip around the clock, where "Paused" is written next to it. */
function clockChip(page: Page): Locator {
  return timer(page).locator("..");
}

/** Seconds on the clock, from "mm:ss / mm:ss". */
async function readClock(page: Page): Promise<number> {
  const text = (await timer(page).textContent()) ?? "";
  const match = /(\d+):(\d+) \//.exec(text);
  expect(match, `timer text: ${text}`).not.toBeNull();
  return Number(match![1]) * 60 + Number(match![2]);
}

test("the session clock keeps its pauses across a reload", async ({ page }) => {
  await createAndEnter(page);
  await expect(timer(page)).toBeVisible();

  // Bank a pause of a few seconds.
  await page.getByRole("button", { name: "Pause" }).click();
  await expect(clockChip(page)).toContainText("Paused");
  await page.waitForTimeout(3_000);
  await page.getByRole("button", { name: "Resume" }).click();
  await expect(clockChip(page)).not.toContainText("Paused");
  await page.waitForTimeout(1_500);

  const before = await readClock(page);
  const beforeAt = Date.now();

  await page.reload();
  await enterWorkspace(page);
  await expect(timer(page)).toBeVisible();
  const after = await readClock(page);
  const wall = (Date.now() - beforeAt) / 1000;

  // Without the banked pause the reloaded clock would read ~3 s ahead.
  expect(Math.abs(after - before - wall)).toBeLessThanOrEqual(2);

  // An open pause is still open after a reload, and the clock stays stopped.
  await page.getByRole("button", { name: "Pause" }).click();
  await expect(clockChip(page)).toContainText("Paused");
  const pausedAt = await readClock(page);

  await page.reload();
  await enterWorkspace(page);
  await expect(clockChip(page)).toContainText("Paused");
  await expect(page.getByText(/^Paused\. The panel is waiting/)).toBeVisible();
  const reloadedPaused = await readClock(page);
  expect(Math.abs(reloadedPaused - pausedAt)).toBeLessThanOrEqual(1);
  await page.waitForTimeout(2_200);
  expect(await readClock(page)).toBe(reloadedPaused);
});

test("a run uses the snapshot shown as saved, even after a save raced an edit", async ({
  page,
}) => {
  const id = await createAndEnter(page);
  const runPanel = panel(page, "Save and run");

  await appendToFile(page, "search.py", "# revision one");
  await expect(runPanel.getByText("Unsaved changes")).toBeVisible();

  // Hold the first save's response so the next edit provably lands while the
  // save is in flight.
  await page.route(/\/api\/interviews\/[^/]+\/files$/, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1_500));
    await route.continue();
  });
  const savePromise = saveAndCapture(page);
  await expect(runPanel.getByRole("button", { name: "Saving…" })).toBeVisible();
  const revisionTwo = await appendToFile(page, "search.py", "# revision two");
  const first = await savePromise;
  await page.unroute(/\/api\/interviews\/[^/]+\/files$/);

  // The late response marks the files it carried as saved, not the newer edit.
  await expect(runPanel.getByText(`Saved snapshot ${first.snapshot_id}`)).toBeVisible();
  await expect(runPanel.getByText("Unsaved changes")).toBeVisible();
  await expect(runPanel.getByRole("button", { name: /^Run saved snapshot/ })).toBeDisabled();

  const second = await saveAndCapture(page);
  expect(second.snapshot_id).not.toBe(first.snapshot_id);
  await expect(runPanel.getByText("All changes saved")).toBeVisible();
  await expect(runPanel.getByText(`Saved snapshot ${second.snapshot_id}`)).toBeVisible();

  // A reload replays every `snapshot_saved` on the stream; the panel must
  // still offer the latest one.
  await page.reload();
  await enterWorkspace(page);
  const runButton = runPanel.getByRole("button", { name: /^Run saved snapshot/ });
  await expect(runButton).toContainText(second.snapshot_id.slice(0, 12));
  await expect(runButton).toBeEnabled();

  const [runResponse] = await Promise.all([
    page.waitForResponse(
      (item) => item.request().method() === "POST" && /\/api\/interviews\/[^/]+\/runs$/.test(item.url()),
    ),
    runButton.click(),
  ]);
  expect(runResponse.ok()).toBe(true);
  const run = (await runResponse.json()) as { id: string; snapshot_id: string };
  expect(run.snapshot_id).toBe(second.snapshot_id);

  const snapshot = await page.request.get(`/api/interviews/${id}/snapshots/${run.snapshot_id}`);
  expect(snapshot.ok()).toBe(true);
  const stored = (await snapshot.json()) as { content_hash: string; files: Record<string, string> };
  expect(stored.content_hash).toBe(second.content_hash);
  expect(stored.files["search.py"]).toBe(revisionTwo);
  expect(stored.content_hash).not.toBe(first.content_hash);
});

test("a reload while finishing lands on the assessment once it is ready", async ({ page }) => {
  test.setTimeout(240_000);
  const id = await createAndEnter(page);
  const runPanel = panel(page, "Save and run");

  await saveAndCapture(page);
  await expect(runPanel.getByText("All changes saved")).toBeVisible();

  // A run in flight holds the finish open long enough to reload into it.
  await runPanel.getByRole("button", { name: /^Run saved snapshot/ }).click();
  await expect(runPanel.getByText("A run is in progress.")).toBeVisible();

  await page.locator("header").getByRole("button", { name: "End interview" }).click();
  await page.locator("dialog").getByRole("button", { name: "End interview" }).click();
  await expect(page.getByText(/^Ending the interview/)).toBeVisible();
  await page.waitForTimeout(500);

  await page.reload();
  await expect(page).toHaveURL(new RegExp(`/assessment/${id}$`), { timeout: 60_000 });
  await expect(page.getByRole("heading", { level: 1, name: CANDIDATE_NAME })).toBeVisible({
    timeout: 120_000,
  });
  await expect(page.getByText("Viewing as the candidate")).toBeVisible();
});
