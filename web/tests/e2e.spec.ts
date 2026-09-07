import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * The golden flow, in a browser, end to end.
 *
 * Consent, the workspace, four candidate turns with two runs between them, the
 * changed condition, the assessment, a replay, a correction and a reviewer
 * resolving it — plus the isolation check that a browser holding no capability
 * is refused. The backend runs the scripted model and the local executor (see
 * `playwright.config.ts`), so every reply, every stage transition and every
 * check result below is deterministic; nothing here touches Agora, a real
 * model or an E2B sandbox.
 */

const CANDIDATE_NAME = "Playwright candidate";

const CONSENT_TEXT =
  "I understand that AI interviewers will question me and that my speech and code will be processed to produce an assessment";

/** The fix that makes every check pass: cache the index hits, filter per request. */
const COMPLETE_SOLUTION = readFileSync(
  path.join(
    __dirname,
    "..",
    "..",
    "scenarios",
    "document-search",
    "checks",
    "v1",
    "solutions",
    "complete",
    "search.py",
  ),
  "utf8",
);

/*
 * The four candidate turns. The controller advances the stage from what these
 * cover, so their wording is part of the fixture: turn 1 names the cache-key
 * diagnosis and a release decision (briefing → initial review → investigation),
 * and turns 3 and 4 carry investigation to the changed condition, where the
 * customer administrator introduces the revocation.
 */
const TURNS = {
  diagnosis:
    "The cache key only uses the query, so another company can see our documents. I would not ship this.",
  mechanism:
    "The cached entry is written once and reused for everyone who asks the same thing.",
  fix: "I moved the permission filter after the cache read so every request is checked.",
  release:
    "I would release the safer version today and note the extra index work in the changelog.",
} as const;

const CORRECTED_TEXT =
  "Corrected by the candidate: this is what the panel actually said at the start of the session.";
const RESOLUTION_TEXT = "Checked against the record; the transcript stands as written.";

/** A `Panel` by its heading — the app's card surface has no landmark role. */
function panel(page: Page, heading: string): Locator {
  return page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: heading, exact: true }) });
}

/** As much of Monaco's global as `replaceFile` touches. */
interface MonacoGlobal {
  editor: { getModels(): Array<{ uri: { path: string }; setValue(value: string): void }> };
}

/**
 * Replace one editable file's whole contents.
 *
 * Through Monaco's own model rather than the keyboard: auto-indent rewrites
 * typed Python, and `insertText` still leaves the editor's undo stack holding
 * a half-typed program. A model edit fires `onDidChangeModelContent`, which is
 * what the React binding listens to, so the workspace sees the change exactly
 * as it would from typing.
 */
async function replaceFile(page: Page, fileName: string, contents: string) {
  await page.getByRole("tab", { name: new RegExp(`^${fileName.replace(".", "\\.")}`) }).click();
  await page.waitForFunction(
    (name) => {
      const models = (window as { monaco?: MonacoGlobal }).monaco?.editor.getModels();
      return Boolean(models?.some((model) => model.uri.path.endsWith(name)));
    },
    fileName,
    { timeout: 90_000 },
  );
  await page.evaluate(
    ({ name, text }) => {
      const models = (window as { monaco?: MonacoGlobal }).monaco!.editor.getModels();
      models.find((model) => model.uri.path.endsWith(name))!.setValue(text);
    },
    { name: fileName, text: contents },
  );
}

/** Save the workspace's files and wait for the snapshot the run will use. */
async function save(page: Page) {
  const runPanel = panel(page, "Save and run");
  await runPanel.getByRole("button", { name: "Save", exact: true }).click();
  await expect(runPanel.getByText("All changes saved")).toBeVisible();
  await expect(runPanel.getByText(/^Saved snapshot snap_/)).toBeVisible();
}

/** Run the selected checks and wait for the newest run to report `summary`. */
async function runChecks(page: Page, summary: string) {
  const results = panel(page, "Results");
  await panel(page, "Save and run")
    .getByRole("button", { name: /^Run saved snapshot/ })
    .click();
  await expect(results.getByText(summary)).toBeVisible({ timeout: 90_000 });
}

/**
 * Wait until the transcript holds exactly `count` panel utterances.
 *
 * Counted by the AI disclosure badge, which every one of them carries (PRD
 * section 12), so the assertion is both "the turn landed" and "it is marked as
 * AI". Waiting on the exact number also keeps the candidate from speaking over
 * the panel's proactive follow-up, which the controller abandons the moment
 * the candidate speaks first.
 */
async function waitForPanelTurns(page: Page, count: number) {
  await expect(page.getByRole("log").getByText("AI generated")).toHaveCount(count, {
    timeout: 60_000,
  });
}

/** Say one thing to the panel and wait for the reply to reach the captions. */
async function speak(page: Page, text: string, panelTurns: number) {
  await page.getByLabel("Message the panel").fill(text);
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByRole("log").getByText(text)).toBeVisible();
  await waitForPanelTurns(page, panelTurns);
}

test("the golden flow: consent, workspace, assessment, replay, correction, review", async ({
  page,
  browser,
  baseURL,
}) => {
  test.setTimeout(300_000);

  /* --------------------------------------------------- consent and creation */

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Before you agree" })).toBeVisible();

  await page.getByLabel("Display name or pseudonym").fill(CANDIDATE_NAME);
  await page.getByLabel(CONSENT_TEXT).check();
  await page.getByRole("button", { name: "Create interview" }).click();

  await expect(page.getByRole("heading", { name: "Interview created" })).toBeVisible();
  const reviewerUrl = await page.getByLabel("Reviewer link").inputValue();
  expect(reviewerUrl).toContain("/review/");

  await page.getByRole("link", { name: "Enter workspace" }).click();
  await expect(page).toHaveURL(/\/interview\/itv_[0-9a-f]+$/);
  const interviewId = page.url().split("/").pop()!;

  /* ------------------------------------------------------------- the session */

  await page.getByRole("button", { name: "Continue with text" }).click();
  await expect(page.getByRole("heading", { name: "Save and run" })).toBeVisible();
  // The greeting opens the transcript before anyone has spoken.
  await expect(page.getByRole("log").getByText(CANDIDATE_NAME)).toBeVisible();
  await expect(page.getByText("Briefing")).toBeVisible();

  await speak(page, TURNS.diagnosis, 2);
  await expect(page.getByText("Initial review")).toBeVisible();

  await speak(page, TURNS.mechanism, 3);
  await expect(page.getByText("Investigation")).toBeVisible();

  /* --------------------------------------------- the seeded code, then a fix */

  const runPanel = panel(page, "Save and run");
  await expect(runPanel.getByText("Nothing saved yet")).toBeVisible();
  await expect(
    runPanel.getByRole("checkbox", { name: /Revocation takes effect/ }),
  ).toBeDisabled();

  await save(page);
  await runChecks(page, "1 of 3 checks passed");

  // The check rows inside the newest run entry; anchoring the filter to the
  // start of the row's text picks the check, not the run entry containing it.
  const results = panel(page, "Results");
  await expect(
    results.locator("li").filter({ hasText: /^Cross-company isolation/ }),
  ).toContainText("Failed");
  await expect(
    results.locator("li").filter({ hasText: /^Permission filtering/ }),
  ).toContainText("Passed");

  // The panel raises a run the candidate has gone quiet on, without being asked.
  await waitForPanelTurns(page, 4);

  await replaceFile(page, "search.py", COMPLETE_SOLUTION);
  await expect(runPanel.getByText("Unsaved changes")).toBeVisible();
  await save(page);
  await runChecks(page, "3 of 3 checks passed");

  // The follow-up to the passing run hands the turn to the product manager: a
  // second role, one speech controller (PRD section 9). The header names the
  // role that is speaking; the greeting mentions all three, so the transcript
  // is not where to look for a handoff.
  await waitForPanelTurns(page, 5);
  await expect(page.locator("header").getByText("Product manager")).toBeVisible();

  /* ------------------------------------------------------ the changed condition */

  await speak(page, TURNS.fix, 6);
  await speak(page, TURNS.release, 7);

  await expect(page.getByText("New scenario information:")).toBeVisible();
  await expect(page.locator("header").getByText("Customer administrator")).toBeVisible();
  await expect(page.getByText("Changed condition")).toBeVisible();
  await expect(
    runPanel.getByRole("checkbox", { name: /Revocation takes effect/ }),
  ).toBeEnabled();

  await runChecks(page, "4 of 4 checks passed");

  /* ------------------------------------------------------------------- finish */

  await page.locator("header").getByRole("button", { name: "End interview" }).click();
  await page.locator("dialog").getByRole("button", { name: "End interview" }).click();

  await expect(page).toHaveURL(new RegExp(`/assessment/${interviewId}$`), { timeout: 120_000 });
  await expect(page.getByRole("heading", { level: 1, name: CANDIDATE_NAME })).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByText("Viewing as the candidate")).toBeVisible();

  /* --------------------------------------------------------------- the report */

  const dimensions = page.getByRole("region", { name: "Dimensions" });
  await expect(dimensions.getByRole("heading", { level: 3 })).toHaveCount(4);
  await expect(dimensions.getByRole("heading", { name: "Understanding the problem" })).toBeVisible();

  const findings = page.getByRole("region", { name: "Findings" });
  const findingList = findings.getByRole("list", { name: "Findings" }).getByRole("listitem");
  await expect(findingList.first()).toBeVisible();
  expect(await findingList.count()).toBeGreaterThanOrEqual(1);
  await findingList.first().getByRole("button").click();

  const nodes = page.locator(".react-flow__node");
  await expect(nodes.first()).toBeVisible();
  expect(await nodes.count()).toBeGreaterThanOrEqual(2);

  /* ------------------------------------------------------------------ replay */

  await findings.getByRole("button", { name: /^Run · / }).first().click();
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByRole("tab", { name: "Results" })).toBeVisible();
  await expect(drawer.getByRole("tab", { name: "Code" })).toBeVisible();

  const original = drawer.getByText(/^Completed · \d+ of \d+ checks passed$/);
  const originalOutcome = (await original.textContent())!;
  await expect(drawer.getByText("No reruns yet.")).toBeVisible();

  await drawer.getByRole("button", { name: /^Rerun/ }).click();
  await expect(drawer.getByText("Matches original")).toBeVisible({ timeout: 120_000 });
  // A replay is stored beside the original; it never rewrites it (PRD section 8).
  await expect(original).toHaveText(originalOutcome);

  await drawer.getByRole("button", { name: "Close" }).click();
  await expect(drawer).toHaveCount(0);

  /* -------------------------------------------------------------- correction */

  await findings.getByRole("button", { name: /Greeting$/ }).first().click();
  await expect(drawer.getByRole("heading", { name: "Transcript segment" })).toBeVisible();
  await drawer.getByRole("button", { name: "Flag this segment" }).click();
  await drawer.getByLabel("Corrected text").fill(CORRECTED_TEXT);
  await drawer.getByRole("button", { name: "File correction" }).click();

  await expect(drawer.getByText(CORRECTED_TEXT)).toBeVisible();
  await drawer.getByRole("button", { name: "Close" }).click();
  await expect(page.getByText("Needs review").first()).toBeVisible();

  /* ---------------------------------------------------------------- reviewer */

  const reviewerContext = await browser.newContext();
  const reviewerPage = await reviewerContext.newPage();
  await reviewerPage.goto(reviewerUrl);

  await expect(reviewerPage).toHaveURL(new RegExp(`/assessment/${interviewId}$`));
  await expect(reviewerPage.getByText("Viewing as the reviewer")).toBeVisible({
    timeout: 60_000,
  });
  await expect(reviewerPage.getByText("Needs review").first()).toBeVisible();

  const corrections = reviewerPage.getByRole("region", { name: "Corrections" });
  await corrections.getByLabel(/^Resolution/).fill(RESOLUTION_TEXT);
  await corrections.getByRole("button", { name: "Resolve correction" }).click();

  await expect(corrections.getByText("Resolved")).toBeVisible();
  await expect(reviewerPage.getByText("Needs review")).toHaveCount(0);
  // The candidate's open report follows the resolution over its event stream.
  await expect(page.getByText("Needs review")).toHaveCount(0, { timeout: 60_000 });

  /* --------------------------------------------------------------- isolation */

  const strangerContext = await browser.newContext();
  const refused = await strangerContext.request.get(`${baseURL}/api/interviews/${interviewId}`);
  expect(refused.status()).toBe(401);

  await strangerContext.close();
  await reviewerContext.close();
});
