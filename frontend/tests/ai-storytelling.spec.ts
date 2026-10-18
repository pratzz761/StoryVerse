import { test, expect } from "@playwright/test";

test("AMD consent identifies the selected text provider (mocked health)", async ({ page }) => {
  await page.route("**/api/health", async route => {
    const response = await route.fetch();
    const health = await response.json();
    await route.fulfill({response, json:{...health, ai_enabled:true, ai:{...health.ai, mode:"amd", model:"DeepSeek-V4-Flash"}}});
  });
  await page.goto("/stories/aaaaaaaa-aaaa-4aaa-8aaa-000000000001/continue");
  await expect(page.getByRole("checkbox", {name:/Send my idea.*AMD Token Factory/})).toBeVisible();
  await expect(page.locator(".ai-consent")).toContainText("AMD Radeon Cloud processes this text under its API terms");
  await expect(page.locator(".ai-consent")).not.toContainText("Google");
});

test("AI version, SDXL fallback and image regeneration, final edits, approval and both readers (mocked providers)", async ({ page }, info) => {
  const story = `AI workflow ${info.project.name} ${Date.now()}`;
  await page.goto("/create");
  await page.getByRole("textbox", {name:"Story title",exact:true}).fill(story);
  await page.locator('textarea[name="narrative"]').fill("Elara, a quiet village herbalist, found a brass key beside the river. It belonged to her mother.");
  await page.getByRole("checkbox").check();
  await page.getByRole("button",{name:"Create story",exact:true}).click();
  await page.getByRole("link",{name:"Continue story",exact:true}).click();
  await page.locator("textarea").fill("A mysterious stranger in a grey coat warns Elara that the river is about to flood.");
  await page.getByRole("checkbox",{name:/Send my idea/}).check();
  await page.getByRole("button",{name:"Generate with AI",exact:true}).click();
  await expect(page.getByText("AI test fixture · No live text-model call",{exact:true})).toBeVisible();
  await expect(page.getByTestId("comic-descriptions").locator("figure")).toHaveCount(2);
  await expect(page.getByRole("textbox",{name:"Chapter narrative",exact:true})).toContainText("Elara");
  const previous = page.url();
  await page.getByRole("button",{name:"Regenerate panel 1 description",exact:true}).click();
  await page.getByRole("dialog").getByRole("button",{name:"Generate with AI",exact:true}).click();
  await expect(page).not.toHaveURL(previous);
  await expect(page.getByTestId("comic-descriptions")).toContainText("regenerated close-up description");
  await expect(page.getByRole("link",{name:"Open the previous saved version"})).toBeVisible();
  // A failed image request retains descriptions, then an explicit retry can render.
  await page.route("**/panels/0/image", async route => {
    await route.fulfill({status:503,contentType:"application/json",body:JSON.stringify({detail:"Mocked local SDXL unavailable. Panel descriptions remain available."})});
  }, {times:1});
  await page.getByRole("button",{name:"Generate panel 1 image",exact:true}).click();
  await page.getByRole("dialog").getByRole("button",{name:"Generate image locally",exact:true}).click();
  await expect(page.getByRole("alert").filter({hasText:"Mocked local SDXL unavailable"})).toBeVisible();
  await expect(page.getByTestId("comic-descriptions").locator("figure")).toHaveCount(2);
  for (const action of ["Generate panel 1 image","Regenerate panel 1 image"]) {
    const beforeImage = page.url();
    await page.getByRole("button",{name:action,exact:true}).click();
    await page.getByRole("dialog").getByRole("button",{name:"Generate image locally",exact:true}).click();
    await expect(page).not.toHaveURL(beforeImage);
    await expect(page.getByText("Mocked SDXL test image · No local inference",{exact:true})).toBeVisible();
    const picture = page.getByTestId("comic-descriptions").locator("img");
    await expect(picture).toHaveCount(1);
    await expect(picture).toBeVisible();
    await expect.poll(() => picture.evaluate(img => (img as HTMLImageElement).naturalWidth)).toBe(768);
  }
  await page.getByRole("textbox",{name:"Chapter title",exact:true}).fill("The warning at the bridge");
  await page.getByRole("textbox",{name:"Chapter narrative",exact:true}).fill("Elara kept her mother's brass key and listened to the stranger's warning. She would reach the village before the river rose.\n\nThe compass turned toward the forest.");
  await page.getByRole("button",{name:"Save draft",exact:true}).click();
  await expect(page.locator(".save-state")).toContainText("Saved");
  await page.reload();
  await expect(page.getByRole("textbox",{name:"Chapter title",exact:true})).toHaveValue("The warning at the bridge");
  await page.getByRole("tab",{name:"Preview",exact:true}).click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`test-results/${info.project.name}-ai-studio.png`,fullPage:true});
  await page.getByRole("button",{name:"Approve & publish",exact:true}).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button",{name:"Publish chapter",exact:true}).click();
  await expect(page.getByRole("heading",{name:"The warning at the bridge",exact:true})).toBeVisible();
  await expect(page.locator(".chapter")).toHaveCount(2);
  await expect(page.getByTestId("comic-descriptions").locator("figure")).toHaveCount(2);
  await expect(page.getByText("Mocked AI test fixture · contributor approved",{exact:true})).toBeVisible();
  await expect(page.getByTestId("comic-descriptions").locator("img")).toHaveCount(1);
  await expect(page.locator('.chapter img[src*="/api/uploads/"]')).toHaveCount(1);
  await page.getByRole("button",{name:"Comic book",exact:true}).click();
  await page.getByRole("button",{name:"Next",exact:true}).click();
  await expect(page.getByTestId("comic-descriptions").locator("figure")).toHaveCount(2);
  const publishedImage = page.getByTestId("comic-descriptions").locator("img");
  await expect.poll(() => publishedImage.evaluate(img => (img as HTMLImageElement).naturalWidth)).toBe(768);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test("Gemini quota error preserves the idea and supports explicit retry (mocked provider)", async ({ page }, info) => {
  await page.goto("/stories/aaaaaaaa-aaaa-4aaa-8aaa-000000000001/continue");
  await page.locator("textarea").fill(`TEST_QUOTA_ONCE ${info.project.name}: A stranger warns Elara of the coming flood.`);
  await page.getByRole("checkbox",{name:/Send my idea/}).check();
  await page.getByRole("button",{name:"Generate with AI",exact:true}).click();
  await expect(page.getByText("Demo preview · Your words, unchanged",{exact:true})).toBeVisible();
  await expect(page.getByRole("textbox",{name:"Chapter narrative",exact:true})).toHaveValue(new RegExp(`TEST_QUOTA_ONCE ${info.project.name}`));
  await expect(page.getByRole("button",{name:"Retry AI generation",exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Retry AI generation",exact:true}).click();
  await page.getByRole("dialog").getByRole("button",{name:"Generate with AI",exact:true}).click();
  await expect(page.getByText("AI test fixture · No live text-model call",{exact:true})).toBeVisible();
  await expect(page.getByTestId("comic-descriptions")).toBeVisible();
});
