import { expect, test } from "@playwright/test";

const admin = process.env.DATASLEUTH_E2E_ADMIN;
const password = process.env.DATASLEUTH_E2E_PASSWORD;
const sourcePath = process.env.DATASLEUTH_E2E_SCAN_SOURCE;
const sample =
  process.env.DATASLEUTH_E2E_SCAN_VALUE ??
  "synthetic-browser-person@example.invalid";

test("scan an approved directory and review correlated discoveries", async ({
  page,
}) => {
  test.skip(
    !sourcePath,
    "Set DATASLEUTH_E2E_SCAN_SOURCE to enable the live scan test.",
  );
  if (!admin || !password || !sourcePath)
    throw new Error("Configure the synthetic scan fixture and account.");

  const sourceName = `Synthetic scan ${Date.now()}`;
  const renamedName = `${sourceName} renamed`;
  await page.goto("/sources");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByLabel("Username").fill(admin);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(
    page.getByRole("heading", { name: "Scan Sources" }),
  ).toBeVisible();
  await page.getByLabel("Source name").fill(sourceName);
  await page.getByLabel("Directory path").fill(sourcePath);
  await page.getByRole("button", { name: "Add source" }).click();
  const source = page.getByRole("row").filter({
    has: page.getByRole("rowheader", { name: sourceName, exact: true }),
  });
  await expect(source.getByRole("cell", { name: "Enabled" })).toBeVisible();
  await source.getByRole("button", { name: "Disable" }).click();
  await expect(
    source.getByRole("button", { name: "Start scan" }),
  ).toBeDisabled();
  await source.getByRole("button", { name: "Enable" }).click();
  await source.getByRole("button", { name: "Rename" }).click();
  await page.getByLabel("Source name").fill(renamedName);
  await page.getByRole("button", { name: "Save name" }).click();

  const renamed = page.getByRole("row").filter({
    has: page.getByRole("rowheader", { name: renamedName, exact: true }),
  });
  await renamed.getByRole("button", { name: "Start scan" }).click();
  await expect(
    page.getByRole("heading", { name: "Start a read-only scan" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Confirm and start" }).click();
  await expect(
    page.getByRole("heading", { name: "Scan History" }),
  ).toBeVisible();
  const job = page.getByRole("row").filter({
    has: page.getByRole("rowheader", { name: renamedName, exact: true }),
  });
  await expect(
    job.getByRole("cell", { name: "Completed", exact: true }),
  ).toBeVisible({ timeout: 15_000 });
  await expect(job.getByRole("cell").nth(3)).toHaveText("1");
  await expect(job.getByRole("cell").nth(6)).toHaveText("2");
  await job.getByRole("link", { name: "View 2 findings" }).click();

  await expect(
    page.getByRole("heading", { name: "Discoveries", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Category").selectOption("email");
  await page.getByLabel("Search file or source").fill("synthetic.txt");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.getByRole("row")).toHaveCount(3);
  await page.getByRole("link", { name: "Email", exact: true }).first().click();
  await expect(
    page.getByRole("heading", { name: "Related occurrences (1)" }),
  ).toBeVisible();
  await expect(page.getByText("[redacted]", { exact: true })).toHaveCount(2);
  await expect(page.getByText(sample)).toHaveCount(0);
  await page.getByLabel("Review status").selectOption("confirmed");
  await page.getByRole("button", { name: "Save review" }).click();
  await expect(page.getByLabel("Review history")).toContainText("Confirmed by");
  await page.reload();
  await expect(page.getByLabel("Review status")).toHaveValue("confirmed");
  await expect(page.getByLabel("Review history")).toContainText("Confirmed by");
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Recent scans" }),
  ).toBeVisible();
  const overviewScan = page.getByRole("row").filter({
    has: page.getByRole("rowheader", { name: renamedName, exact: true }),
  });
  await expect(
    overviewScan.getByRole("cell", { name: "Completed", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "View findings awaiting review" })
    .click();
  await expect(page.getByLabel("Review status")).toHaveValue("needs_review");
});
