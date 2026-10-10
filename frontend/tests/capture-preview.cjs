'use strict';
// Optional live-network visual evidence; deterministic acceptance is separate.
const {chromium} = require('playwright');
const path = require('node:path');
(async()=>{
 const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL || 'chrome',headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1280,height:900}});
  await page.goto(process.env.CARE_LEARN_URL || 'http://127.0.0.1:4173');
  await page.waitForSelector('[data-center]');
  await page.waitForFunction(()=>document.querySelectorAll('.leaflet-tile-loaded').length>0,{},{timeout:20000});
  await page.locator('[data-center="medanta"]').click();
  await page.locator('#close-details').evaluate(el=>el.blur());
  await page.evaluate(()=>window.scrollTo(0,0));
  const output=path.resolve(__dirname,'../../dev/verification');
  await page.screenshot({path:path.join(output,'caregiving-phase7-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.locator('[data-center="udayan-manesar"]').click();
  await page.locator('#close-details').evaluate(el=>el.blur());
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:path.join(output,'caregiving-phase7-mobile.png'),fullPage:true});
  console.log('Live OSM tiles loaded; desktop and phone evidence saved.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
