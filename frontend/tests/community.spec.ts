import {test, expect} from "@playwright/test";

test("persisted community library, reading resume and published character facts", async ({page}, info) => {
  const sid = "aaaaaaaa-aaaa-4aaa-8aaa-000000000001";
  for (const kind of ["like", "bookmark", "follow"]) await page.request.post(`/api/stories/${sid}/interactions`, {data:{kind,active:false}});
  await page.goto(`/stories/${sid}`);
  const community = page.getByRole("region", {name:"Story community"});
  await community.getByRole("button", {name:/^Like /}).click();
  await expect(community.getByRole("button", {name:/^Liked /})).toHaveAttribute("aria-pressed","true");
  await community.getByRole("button", {name:/^Bookmark /}).click();
  await community.getByRole("button", {name:/^Follow story /}).click();
  await page.reload();
  await expect(community.getByRole("button", {name:/^Bookmarked /})).toHaveAttribute("aria-pressed","true");
  await expect(community.getByRole("button", {name:/^Following story /})).toHaveAttribute("aria-pressed","true");
  await page.getByText("Story Bible · Characters & continuity", {exact:true}).click();
  await expect(page.locator(".story-bible")).toContainText("Personality:");
  await expect(page.locator(".story-bible")).toContainText("spectacles");
  await expect(page.locator(".story-bible")).toContainText("Important events");
  await page.goto("/profile");
  await page.getByRole("tab", {name:/^Bookmarked/}).click();
  await expect(page.locator(".story-card").filter({hasText:"The Forest That Remembers"})).toHaveCount(1);
  await page.getByRole("tab", {name:/^Followed/}).click();
  await expect(page.locator(".story-card").filter({hasText:"The Forest That Remembers"})).toHaveCount(1);
  // A separate three-chapter manual story isolates progress between browser projects.
  const created = await page.request.post("/api/stories", {data:{title:`Reading test ${info.project.name}`,genre:"Fantasy",narrative:"A traveler finds a bridge at dawn."}});
  const storyId = (await created.json()).id;
  for (const version of [1,2]) {
    const draft = await page.request.post(`/api/stories/${storyId}/contributions`,{data:{text:`Hand-written chapter ${version+1}: the traveler follows a distant bell.`,expected_version:version}});
    await page.request.post(`/api/drafts/${(await draft.json()).id}/publish`,{data:{expected_version:version,approved:true}});
  }
  await page.goto(`/stories/${storyId}`);
  await page.getByRole("button", {name:"Comic book",exact:true}).click();
  await page.getByRole("button", {name:"Mark chapter 1 read",exact:true}).click();
  await expect(page.getByRole("region",{name:"Reading progress"})).toContainText("Read through chapter 1 of 3");
  await page.getByRole("button", {name:"Continue reading",exact:true}).click();
  await expect(page.getByRole("navigation",{name:"Chapter navigation"})).toContainText("Chapter 2 of 3");
  await page.getByRole("button", {name:"Mark chapter 2 read",exact:true}).click();
  await page.goto("/profile");
  await page.getByRole("tab",{name:/^Continue reading/}).click();
  const reading = page.locator(".story-card").filter({hasText:`Reading test ${info.project.name}`});
  await reading.getByRole("link",{name:/Continue reading · Chapter 3/}).click();
  await expect(page.getByRole("navigation",{name:"Chapter navigation"})).toContainText("Chapter 3 of 3");
  await expect(page.getByRole("button",{name:"Comic book",exact:true})).toHaveAttribute("aria-pressed","true");
  await page.getByRole("button",{name:"Previous",exact:true}).click();
  await expect(page.getByRole("navigation",{name:"Chapter navigation"})).toContainText("Chapter 2 of 3");
  await page.getByRole("button",{name:"Webtoon",exact:true}).click();
  await expect(page.locator(".chapter")).toHaveCount(3);
  await expect.poll(() => page.evaluate(() => document.activeElement?.classList.contains("chapter"))).toBe(true);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => window.scrollTo({top:0,behavior:"instant"}));
  await page.screenshot({path:`test-results/${info.project.name}-phase-3-reader.png`,fullPage:true});
  // Verify removal also persists to the library.
  for (const kind of ["like", "bookmark", "follow"]) await page.request.post(`/api/stories/${sid}/interactions`, {data:{kind,active:false}});
  await page.goto("/profile");
  await page.getByRole("tab",{name:/^Bookmarked/}).click();
  await expect(page.locator(".story-card").filter({hasText:"The Forest That Remembers"})).toHaveCount(0);
});

test("discovery pagination, recent updates, filters and empty results", async ({page}, info) => {
  await page.goto("/?q=Pagination%20fixture");
  await expect(page.locator(".story-card")).toHaveCount(12);
  const first = await page.locator(".story-title").allTextContents();
  await page.getByRole("button",{name:"Next stories",exact:true}).click();
  await expect(page.locator(".story-card")).toHaveCount(6);
  const second = await page.locator(".story-title").allTextContents();
  expect(first.some(title=>second.includes(title))).toBe(false);
  await page.reload();
  await expect(page.locator(".story-title")).toHaveText(second);
  await page.getByRole("button",{name:"Horror",exact:true}).click();
  await expect(page.getByRole("navigation",{name:"Story pages"})).toContainText("Page 1 of 2");
  await page.getByRole("tab",{name:"Recent",exact:true}).click();
  await expect(page.locator(".story-card")).toHaveCount(12);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path:`test-results/${info.project.name}-phase-3-discovery.png`,fullPage:true});
  await page.getByRole("textbox",{name:"Search stories"}).fill("no such story 987654321");
  await page.getByRole("textbox",{name:"Search stories"}).press("Enter");
  await expect(page.getByRole("heading",{name:"No stories in this corner. Yet."})).toBeVisible();
});
