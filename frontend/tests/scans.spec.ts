import { expect, test } from "@playwright/test";

const admin = process.env.DATASLEUTH_E2E_ADMIN;
const password = process.env.DATASLEUTH_E2E_PASSWORD;
const sourcePath = process.env.DATASLEUTH_E2E_SCAN_SOURCE;

test("register an approved directory and see real scan counts", async ({
  page,
}) => {
  test.skip(
    !sourcePath,
    "Set DATASLEUTH_E2E_SCAN_SOURCE to enable the live scan test.",
  );
  if (!admin || !password || !sourcePath)
    throw new Error("Configure the synthetic scan fixture and account.");

  await page.goto("/sources");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByLabel("Username").fill(admin);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(
    page.getByRole("heading", { name: "Scan Sources" }),
  ).toBeVisible();
  await page.getByLabel("Source name").fill("Synthetic browser scan");
  await page.getByLabel("Directory path").fill(sourcePath);
  await page.getByRole("button", { name: "Add source" }).click();
  const source = page.getByRole("row", { name: /Synthetic browser scan/ });
  await expect(source.getByRole("cell", { name: "Enabled" })).toBeVisible();
  await source.getByRole("button", { name: "Disable" }).click();
  await expect(
    source.getByRole("button", { name: "Start scan" }),
  ).toBeDisabled();
  await source.getByRole("button", { name: "Enable" }).click();
  await source.getByRole("button", { name: "Rename" }).click();
  await page.getByLabel("Source name").fill("Synthetic scan fixture");
  await page.getByRole("button", { name: "Save name" }).click();

  const renamed = page.getByRole("row", { name: /Synthetic scan fixture/ });
  await renamed.getByRole("button", { name: "Start scan" }).click();
  await expect(
    page.getByRole("heading", { name: "Start a read-only scan" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Confirm and start" }).click();
  await expect(
    page.getByRole("heading", { name: "Scan History" }),
  ).toBeVisible();
  const job = page.getByRole("row", { name: /Synthetic scan fixture/ });
  await expect(
    job.getByRole("cell", { name: "Completed", exact: true }),
  ).toBeVisible({ timeout: 15_000 });
  await expect(job.getByRole("cell").nth(3)).toHaveText("1");
  await expect(job.getByRole("cell").nth(6)).toHaveText("1");
});
