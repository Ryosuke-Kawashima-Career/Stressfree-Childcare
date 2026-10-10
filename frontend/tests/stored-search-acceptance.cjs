const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.CARE_LEARN_URL || 'http://127.0.0.1:4174';
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try {
  const page=await browser.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://tile.openstreetmap.org/**',r=>r.abort());
  let calls=0,hold=false;
  await page.route('**/api/discover',async r=>{
   calls++;
   assert.ok(r.request().postDataJSON().savedScopeId);
   if(hold) await new Promise(resolve=>setTimeout(resolve,400));
   await r.fulfill({status:503,json:{error:{message:'Live retrieval unavailable.'}}});
  });
  const response=await page.request.post(base+'/api/reveal',{data:{query:'hospitals in Gurgaon',category:'health',area:'Gurugram'}});
  const saved=await response.json();assert.ok(saved.items.length>=2);
  async function synced(ids){
   await page.waitForFunction(ids=>JSON.stringify([...document.querySelectorAll('[data-center]')].map(n=>n.dataset.center).sort())===JSON.stringify(ids),ids.slice().sort());
   assert.deepEqual(await page.locator('[data-pin]').evaluateAll(ns=>ns.map(n=>n.dataset.pin).sort()),ids.slice().sort());
  }
  await page.goto(base);await page.waitForSelector('[data-center]');
  await page.locator('[data-category="health"]').click();
  await page.locator('#search').fill('Artemis');await page.locator('#search').press('Enter');
  await synced(['artemis']);assert.equal(calls,0);
  await page.locator('#search').fill('hospitals in Gurgaon');await page.locator('#search').press('Enter');
  const ids=saved.items.map(p=>p.id);await synced(ids);assert.equal(calls,0);
  assert.ok((await page.locator('#search-status').innerText()).includes('Stored results'));
  for(const provider of saved.items) assert.deepEqual(await page.evaluate(id=>{const p=markers.get(id).getLatLng();return [p.lat,p.lng];},provider.id),[provider.latitude,provider.longitude]);
  await page.locator('#refresh-search').click();
  await page.waitForFunction(()=>document.querySelector('#search-status').textContent.includes('Live retrieval unavailable'));
  await synced(ids);assert.equal(calls,1);
  await page.locator('#search').fill('');await page.locator('#search').press('Enter');
  await page.waitForFunction(()=>document.querySelector('#submit-search').disabled===false);
  await synced(ids);assert.equal(calls,1);
  await page.locator('#search').fill('hospitals');await page.locator('#search').press('Enter');
  await page.waitForFunction(()=>document.querySelector('#submit-search').disabled===false);
  hold=true;await page.locator('#refresh-search').click();await page.locator('#reset').click();
  await page.waitForTimeout(600);
  assert.equal(await page.locator('#search').inputValue(),'');
  assert.ok(!(await page.locator('#search-status').innerText()).includes('Live retrieval unavailable'));
  assert.deepEqual(errors,[]);
  console.log('PASS: real saved hospitals revealed beyond old scope, no AI on submit/blank, exact pins, failed refresh retention and reset race');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
