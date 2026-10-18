// Read-only screenshots and responsive QA of the running app.
// Usage: node tests/capture-preview.mjs [http://127.0.0.1:3000]
import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
const base = process.argv[2] || 'http://127.0.0.1:3000';
const browser = await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL || (process.platform==='win32' ? 'msedge' : 'chromium')});
await mkdir('../docs/screenshots',{recursive:true});
try {
  for (const width of [390,768,1024,1440]) {
    const page=await browser.newPage({viewport:{width,height:1000},deviceScaleFactor:1});
    for (const route of ['/', '/create']) {
      await page.goto(base+route);
      await page.waitForSelector(route==='/' ? '.story-card' : '.editor-card');
      if (route==='/') {
        for (const image of await page.locator('.story-cover').all()) {
          await image.scrollIntoViewIfNeeded();
          await image.evaluate(i=>i.decode());
        }
        await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
      }
      const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
      if (overflow) throw new Error(`Page overflow at ${width}px: ${route}`);
      if (route==='/' && (width===390 || width===1440)) await page.screenshot({path:`../docs/screenshots/explore-${width}.png`,fullPage:true});
    }
    await page.close();
  }
  console.log('PASS: production feed/create layouts at 390, 768, 1024 and 1440px; preview screenshots saved.');
} finally { await browser.close(); }
