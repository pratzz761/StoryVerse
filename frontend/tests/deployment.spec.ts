import {test,expect} from '@playwright/test';

test('remote worker offline error, asynchronous result and recovery preserve the draft (mocked providers)',async({page,request})=>{
 const story=await (await request.get('/api/stories/aaaaaaaa-aaaa-4aaa-8aaa-000000000001')).json();
 const idea=await (await request.post(`/api/stories/${story.id}/contributions`,{data:{text:'A traveler arrives.',expected_version:story.version}})).json();
 const generated=await (await request.post(`/api/drafts/${idea.id}/generate`,{data:{request_id:crypto.randomUUID(),expected_revision:0,consent:true}})).json();
 await page.goto(`/studio/${generated.id}`);
 await page.route('**/panels/0/image',route=>route.fulfill({status:503,json:{code:'worker_offline',detail:'The local image worker is offline. Descriptions and previous images are safe.'}}),{times:1});
 const generate=async()=>{await page.getByRole('button',{name:'Generate panel 1 image',exact:true}).click();await page.getByRole('dialog').getByRole('button',{name:'Generate image locally',exact:true}).click();};
 await generate();
 await expect(page.getByRole('alert').filter({hasText:'worker is offline'})).toBeVisible();
 await expect(page.getByTestId('comic-descriptions').locator('figure')).toHaveCount(2);
 let resultId='',polls=0;
 await page.route('**/panels/0/image',async route=>{
   const real=await route.fetch();expect(real.ok()).toBeTruthy();resultId=(await real.json()).id;
   await route.fulfill({status:202,json:{job_id:'aaaaaaaa-aaaa-4aaa-8aaa-000000000099',status:'queued'}});
 });
 await page.route('**/api/image-jobs/*',route=>route.fulfill({json:++polls===1?{status:'running'}:{status:'succeeded',id:resultId}}));
 await generate();
 await expect(page).not.toHaveURL(new RegExp(generated.id));
 await expect(page.getByTestId('comic-descriptions').locator('img')).toHaveCount(1);
 expect(polls).toBeGreaterThanOrEqual(2);
 // Reopening a source draft resumes its durable queued job rather than rerendering.
 await page.route(`**/api/drafts/${generated.id}`,async route=>{
  if(route.request().method()!=='GET')return route.continue();
  const r=await route.fetch();await route.fulfill({json:{...await r.json(),pending_image_job:'aaaaaaaa-aaaa-4aaa-8aaa-000000000099'}});
 });
 await page.goto(`/studio/${generated.id}`);await expect(page).toHaveURL(new RegExp(resultId));
});

test('moderator review controls and community guidelines (mocked moderation responses)',async({page})=>{
 let hidden=false;
 await page.route('**/api/moderation/reports',route=>route.fulfill({json:[{id:'report',story_id:'aaaaaaaa-aaaa-4aaa-8aaa-000000000001',title:'Reported fixture',reason:'spam',details:'Mocked report details',status:hidden?'reviewed':'open',is_hidden:hidden}]}));
 await page.route('**/api/moderation/stories/*',async route=>{const body=route.request().postDataJSON();expect(body.reason).toBe('Reviewed spam report');hidden=body.hidden;await route.fulfill({json:{hidden}});});
 await page.goto('/moderation');
 await page.getByRole('textbox',{name:'Moderation reason'}).fill('Reviewed spam report');
 await page.getByRole('button',{name:'Hide public story'}).click();
 await expect(page.getByRole('button',{name:'Restore public story'})).toBeVisible();
 await page.goto('/guidelines');await expect(page.getByRole('heading',{name:'Community guidelines'})).toBeVisible();
});
