const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.CARE_LEARN_URL || 'http://127.0.0.1:4174';
(async () => {
 const browser = await chromium.launch({headless:true,channel:'chrome'});
 try {
  const page = await browser.newPage();
  const errors=[]; page.on('pageerror', e=>errors.push(e.message));
  await page.route('https://tile.openstreetmap.org/**',r=>r.abort());
  const records=JSON.parse(fs.readFileSync('backend/data/providers.json','utf8'));
  const discovered={...records[0],id:'new-provider',name:'Discovered Hospital',relevanceReason:'Pediatric care',citations:[{url:'https://www.medanta.org/contact-us',title:'Provider services',fields:['services']}]};
  let calls=0, fail=false, hold=false;
  const scopeId='a'.repeat(64);
  await page.route('**/api/reveal',r=>r.fulfill({json:{items:[],total:0,directoryCounts:{health:3,learning:2},scopeId:'b'.repeat(64),retrievedAt:'2026-10-10T10:00:00Z',retrievalStatus:'stored',warnings:[]}}));
  await page.route('**/api/discover', async r=>{
   calls++;
   assert.ok(!('origin' in r.request().postDataJSON()));
   if(hold) await new Promise(resolve=>setTimeout(resolve,400));
   if(fail) return r.fulfill({status:503,json:{error:{code:'ai_not_configured',message:'AI discovery is not configured on the server.'}}});
   await r.fulfill({json:{items:[discovered],total:1,directoryCounts:{health:3,learning:2},scopeId,retrievedAt:'2026-10-10T10:00:00Z',retrievalStatus:'fresh',warnings:[]}});
  });
  await page.route('**/api/search', async r=>{
   const body=r.request().postDataJSON();
   if(!body.scopeId) return r.continue();
   assert.equal(body.scopeId,scopeId);
   const items=(body.category==='learning'||body.cost==='free')?[]:[discovered];
   await r.fulfill({json:{items,total:items.length,directoryCounts:{health:3,learning:2}}});
  });
  const directoryResponse=await page.request.post(base+'/api/search',{data:{}});
  const initialCount=(await directoryResponse.json()).total;
  await page.goto(base);
  await page.waitForSelector('[data-center]');
  assert.equal(await page.locator('#search-form').count(),1);
  async function synced(n){await page.waitForFunction(n=>document.querySelectorAll('[data-center]').length===n,n);const ids=await page.locator('[data-center]').evaluateAll(ns=>ns.map(n=>n.dataset.center).sort());assert.deepEqual(await page.locator('[data-pin]').evaluateAll(ns=>ns.map(n=>n.dataset.pin).sort()),ids);}
  await synced(initialCount);
  await page.locator('#search').fill('children needing pediatric care');
  assert.equal(calls,0);
  await page.locator('#search').press('Enter');
  await page.waitForSelector('[data-center="new-provider"]');
  await synced(1);
  assert.equal(await page.locator('#search').inputValue(),'children needing pediatric care');
  await page.locator('[data-center="new-provider"]').click();
  assert.ok((await page.locator('#details').innerText()).includes('Pediatric care'));
  assert.ok((await page.locator('#details').innerText()).includes(discovered.latitude.toFixed(6)));
  assert.ok((await page.locator('#details').innerText()).includes(discovered.longitude.toFixed(6)));
  assert.deepEqual(await page.evaluate(()=>{const p=markers.get('new-provider').getLatLng();return [p.lat,p.lng];}),[discovered.latitude,discovered.longitude]);
  assert.ok(await page.locator('#details a').count()>0);
  await page.locator('[data-category="learning"]').click();await synced(0);assert.equal(calls,1);
  await page.locator('[data-category="all"]').click();await synced(1);
  await page.locator('#cost').selectOption('free');await synced(0);assert.equal(calls,1);
  await page.locator('#cost').selectOption('all');await synced(1);
  fail=true;
  await page.locator('[data-center="new-provider"]').click();
  await page.locator('#refresh-search').click();
  await page.waitForFunction(()=>document.querySelector('#search-status').textContent.includes('Previous results'));
  assert.equal(await page.locator('#close-details').count(),1);await synced(1);
  fail=false;hold=true;
  await page.locator('#retry-search').click();
  await page.locator('#reset').click();await synced(initialCount);
  await page.waitForTimeout(600);await synced(initialCount);
  for(const width of [320,390,760,1280]){await page.setViewportSize({width,height:900});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));}
  const wrongServer = await browser.newPage();
  await wrongServer.route('https://tile.openstreetmap.org/**',r=>r.abort());
  await wrongServer.route('**/api/search',r=>r.fulfill({status:501,contentType:'text/html',body:'<!DOCTYPE HTML><html>Unsupported method POST</html>'}));
  await wrongServer.goto(base);
  await wrongServer.waitForFunction(()=>document.querySelector('#retry-search')?.hidden===false);
  assert.ok((await wrongServer.locator('#search-status').innerText()).includes('Start the FastAPI backend'));
  assert.ok(!(await wrongServer.locator('#search-status').innerText()).includes('Unexpected token'));
  assert.equal(await wrongServer.locator('[data-center]').count(),0);
  await wrongServer.close();
  assert.deepEqual(errors,[]);
  console.log('PASS: submit, cited results, scoped filters, errors, selection, reset race, map/list and responsive layout');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
