import { expect, test, type Page } from "@playwright/test";

const password = process.env.DATASLEUTH_E2E_PASSWORD;
const admin = process.env.DATASLEUTH_E2E_ADMIN;
const viewer = process.env.DATASLEUTH_E2E_VIEWER;

async function fillCredentials(
  page: Page,
  username: string,
  passphrase: string,
) {
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(passphrase);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("direct visits require sign-in and the form rejects empty credentials", async ({
  page,
}) => {
  await page.goto("/accounts");
  await expect(page).toHaveURL(/\/sign-in$/);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByLabel("Username")).toBeFocused();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

test("administrator signs in, restores the session, and signs out", async ({
  page,
}) => {
  if (!admin || !password)
    throw new Error("Configure synthetic browser test accounts.");
  await page.goto("/accounts");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await fillCredentials(page, admin, "wrong synthetic passphrase");
  await expect(page.getByRole("alert")).toHaveText(
    "Invalid username or password.",
  );
  await expect(page.getByLabel("Password")).toHaveValue("");

  await fillCredentials(page, admin, password);
  await expect(page).toHaveURL(/\/accounts$/);
  await expect(page.getByRole("cell", { name: admin })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("cell", { name: admin })).toBeVisible();
  const session = (await page.context().cookies()).find(
    (cookie) => cookie.name === "datasleuth_session",
  );
  expect(session?.httpOnly).toBe(true);
  expect(session?.sameSite).toBe("Strict");
  expect(session?.path).toBe("/api/v1");

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/sign-in$/);
  await page.goto("/accounts");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

test("viewer receives a permission denial for the direct URL and API", async ({
  page,
}) => {
  if (!viewer || !password)
    throw new Error("Configure synthetic browser test accounts.");
  await page.goto("/accounts");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await fillCredentials(page, viewer, password);
  await expect(page.getByRole("alert")).toHaveText(
    "Administrator access is required.",
  );
  await expect(page.getByRole("link", { name: "Accounts" })).toHaveCount(0);
  expect((await page.request.get("/api/v1/auth/users")).status()).toBe(403);
});

test("a lost session redirects an open tab to sign-in", async ({ page }) => {
  if (!viewer || !password)
    throw new Error("Configure synthetic browser test accounts.");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await fillCredentials(page, viewer, password);
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await page.context().clearCookies({ name: "datasleuth_session" });
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page).toHaveURL(/\/sign-in$/);
});

test("one user has different permissions in a second organisation", async ({
  page,
}) => {
  const organisation = process.env.DATASLEUTH_E2E_ORGANISATION;
  test.skip(
    !organisation,
    "Set a second organisation with a viewer membership for the admin.",
  );
  if (!admin || !password || !organisation)
    throw new Error("Configure the synthetic memberships.");
  await page.goto("/accounts");
  await page.getByText("Sign in to another organisation").click();
  await page.getByLabel("Organisation ID").fill(organisation);
  await fillCredentials(page, admin, password);
  await expect(page.getByRole("alert")).toHaveText(
    "Administrator access is required.",
  );
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  expect(me.organisation_id).toBe(organisation);
  expect(me.role).toBe("viewer");
  expect((await page.request.get("/api/v1/auth/users")).status()).toBe(403);
  await page.reload();
  await expect(page.getByRole("alert")).toHaveText(
    "Administrator access is required.",
  );
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.goto("/accounts");
  await fillCredentials(page, admin, password);
  await expect(page.getByRole("cell", { name: admin })).toBeVisible();
});
