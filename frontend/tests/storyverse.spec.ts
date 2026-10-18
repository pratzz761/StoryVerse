import { test, expect } from "@playwright/test";

async function noOverflow(page: import("@playwright/test").Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

test("explore filters, search, reader layouts and navigation", async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto("/");
  const sampleCards = page.locator(".story-card").filter({ hasText: "Demo story" });
  await expect(page.getByRole("heading", { name: "Good stories don't end here." })).toBeVisible();
  await expect(sampleCards).toHaveCount(6);
  for (const cover of await page.locator(".story-cover").all()) {
    await cover.scrollIntoViewIfNeeded();
    await cover.evaluate(image => (image as HTMLImageElement).decode());
  }
  await page.evaluate(() => window.scrollTo({top:0,behavior:"instant"}));
  await page.screenshot({ path: `test-results/${info.project.name}-explore.png`, fullPage: true });
  await noOverflow(page);
  await page.getByRole("button", { name: "Mystery", exact: true }).click();
  await expect(sampleCards).toHaveCount(1);
  await expect(page.getByRole("heading", { name: "The Last Light in Kyoto" })).toBeVisible();
  await page.getByRole("button", { name: "All genres" }).click();
  await page.getByRole("tab", { name: "Recent" }).click();
  await expect(sampleCards).toHaveCount(6);
  await page.getByRole("textbox", { name: "Search stories" }).fill("forest");
  await page.getByRole("textbox", { name: "Search stories" }).press("Enter");
  await expect(page.locator(".story-card")).toHaveCount(1);
  await page.locator(".story-title").click();
  await expect(page.getByRole("heading", { name: "The Forest That Remembers", exact: true })).toBeVisible();
  await expect(page.locator(".chapter")).toHaveCount(3);
  await page.getByRole("button", { name: "Comic book", exact: true }).click();
  await expect(page.locator(".chapter")).toHaveCount(1);
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByRole("heading", { name: "The keeper of small things", exact: true })).toBeVisible();
  await page.screenshot({ path: `test-results/${info.project.name}-reader.png`, fullPage: true });
  await noOverflow(page);
  await page.getByRole("button", { name: "Webtoon", exact: true }).click();
  await expect(page.locator(".chapter")).toHaveCount(3);
  expect(errors).toEqual([]);
});

test("create, upload, contribute, save, preview and explicitly publish", async ({ page }, info) => {
  const title = `A Door in the Rain ${info.project.name} ${Date.now()}`;
  await page.goto("/create");
  await page.getByRole("textbox", { name: "Story title", exact: true }).fill(title);
  await page.getByRole("combobox", { name: "Genre", exact: true }).selectOption("Mystery");
  await page.locator('textarea[name="narrative"]').fill("The door appeared every time it rained. This time, someone knocked from the other side.");
  await page.getByLabel("Upload attachments").setInputFiles({ name: "rain.png", mimeType: "image/png", buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a4Z8AAAAASUVORK5CYII=", "base64") });
  await expect(page.locator(".attachment-list")).toContainText("rain.png");
  await page.getByRole("checkbox").check();
  await noOverflow(page);
  await page.getByRole("button", { name: "Create story", exact: true }).click();
  await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
  await expect(page.locator(".comic-panels img")).toHaveCount(1);
  await page.getByRole("link", { name: "Continue story", exact: true }).click();
  await expect(page.getByText("Previous chapter summary", { exact: true })).toBeVisible();
  await page.locator("textarea").fill("Mira took one step into the light. The rain stopped, but the knocking did not.");
  await page.getByRole("radio", { name: "Add a twist", exact: true }).check();
  await page.getByRole("button", { name: "Generate preview", exact: true }).click();
  await expect(page.getByText("Demo preview · Your words, unchanged", { exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "Chapter title", exact: true }).fill("The other side");
  await page.getByRole("textbox", { name: "Chapter narrative", exact: true }).fill("Mira stepped into the light. Beyond the door, another world was waiting.");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.locator(".save-state")).toContainText("Saved");
  await page.reload();
  await expect(page.getByRole("textbox", { name: "Chapter title", exact: true })).toHaveValue("The other side");
  await page.getByRole("tab", { name: "Preview", exact: true }).click();
  await expect(page.locator(".studio-prose")).toContainText("another world was waiting");
  await page.screenshot({ path: `test-results/${info.project.name}-studio.png`, fullPage: true });
  await noOverflow(page);
  await page.getByRole("button", { name: "Approve & publish", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Publish chapter", exact: true }).click();
  await expect(page.getByRole("heading", { name: "The other side", exact: true })).toBeVisible();
  await expect(page.locator(".chapter")).toHaveCount(2);
  await page.goto("/profile");
  await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
  await page.getByRole("tab", { name: /Contributed stories/ }).click();
  await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
  await noOverflow(page);
});

test("private drafts, profile editing and honest preview regeneration", async ({ page }, info) => {
  await page.goto("/stories/aaaaaaaa-aaaa-4aaa-8aaa-000000000001/continue");
  await page.locator("textarea").fill(`Original contribution from ${info.project.name}.`);
  await page.getByRole("button", { name: "Generate preview", exact: true }).click();
  await page.getByRole("textbox", { name: "Chapter title", exact: true }).fill("An edited draft");
  await page.getByRole("button", { name: "Regenerate preview", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("doesn't generate new text");
  await page.getByRole("button", { name: "Reset preview", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Chapter title", exact: true })).toHaveValue("Chapter 4");
  await page.goto("/drafts");
  await expect(page.locator(".draft-list")).toContainText("The Forest That Remembers");
  await page.goto("/profile");
  await page.getByRole("button", { name: "Edit profile", exact: true }).click();
  await page.getByRole("textbox", { name: "Bio", exact: true }).fill("One more chapter, always.");
  await page.getByRole("button", { name: "Save profile", exact: true }).click();
  await expect(page.locator(".profile-identity")).toContainText("One more chapter, always.");
  await page.reload();
  await expect(page.locator(".profile-identity")).toContainText("One more chapter, always.");
  await noOverflow(page);
});
