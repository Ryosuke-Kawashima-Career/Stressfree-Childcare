'use strict';
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname,'../..');
const output = path.join(root,'dev/verification');
const base = process.env.CARE_LEARN_URL || 'http://127.0.0.1:4173';
const report = {date:'2026-10-10',phase:7,checks:[],consoleErrors:[],widths:[]};
function pass(name) {report.checks.push(name);console.log('PASS',name);}
async function synchronized(page, expected) {
  await page.waitForFunction(n=>document.querySelectorAll('[data-center]').length===n,expected);
  const list = await page.locator('[data-center]').evaluateAll(nodes=>nodes.map(n=>n.dataset.center).sort());
  const pins = await page.locator('[data-pin]').evaluateAll(nodes=>nodes.map(n=>n.dataset.pin).sort());
  assert.deepEqual(pins,list);assert.equal(list.length,expected);
}
(async()=>{
  const browser = await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL || 'chrome'});
  try {
    // Deterministic map transport; live tiles are checked separately.
    const pixel = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII=', 'base64');
    async function newTestPage(options) {
      const testPage=await browser.newPage(options);
      await testPage.route('https://tile.openstreetmap.org/**', route=>route.fulfill({status:200,contentType:'image/png',body:pixel}));
      let dataset=JSON.parse(fs.readFileSync(path.join(root,'backend/data/providers.json'),'utf8'));
      const scopes=new Map();
      testPage.setDataset = records => {dataset=records;};
      await testPage.route('**/api/reveal', async route=>{
        const body=route.request().postDataJSON();
        const items=dataset.filter(c=>[c.name,c.providerType,c.address,c.locality,...c.services].join(' ').toLowerCase().includes(body.query.toLowerCase().trim()));
        const scopeId=require('node:crypto').createHash('sha256').update('stored:'+body.query).digest('hex');scopes.set(scopeId,items);
        await route.fulfill({json:{items,total:items.length,directoryCounts:{health:dataset.filter(c=>c.category==='health').length,learning:dataset.filter(c=>c.category==='learning').length},scopeId,retrievedAt:'2026-10-10T10:00:00Z',retrievalStatus:'stored',warnings:[]}});
      });
      await testPage.route('**/api/discover', async route=>{
        const body=route.request().postDataJSON();
        const items=dataset.filter(c=>[c.name,c.providerType,c.address,c.locality,...c.services].join(' ').toLowerCase().includes(body.query.toLowerCase().trim()));
        const scopeId=require('node:crypto').createHash('sha256').update(body.query).digest('hex');scopes.set(scopeId,items);
        await route.fulfill({json:{items,total:items.length,directoryCounts:{health:dataset.filter(c=>c.category==='health').length,learning:dataset.filter(c=>c.category==='learning').length},scopeId,retrievedAt:'2026-10-10T10:00:00Z',retrievalStatus:'fresh',warnings:[]}});
      });
      await testPage.route('**/api/search', async route=>{
        const b=route.request().postDataJSON();
        const items=(b.scopeId?scopes.get(b.scopeId):dataset).filter(c=>(b.category==='all'||c.category===b.category)&&(b.cost==='all'||c.costStatus===b.cost)&&(!b.serviceTag||c.serviceTags.includes(b.serviceTag)));
        await route.fulfill({json:{items,total:items.length,directoryCounts:{health:dataset.filter(c=>c.category==='health').length,learning:dataset.filter(c=>c.category==='learning').length}}});
      });
      return testPage;
    }
    const page = await newTestPage({viewport:{width:1280,height:900}});
    page.on('pageerror',error=>report.consoleErrors.push(error.message));
    await page.goto(base);await page.waitForSelector('[data-center]');
    await synchronized(page,4);
    assert.equal(await page.locator('#hospital-total').innerText(),'2');
    assert.equal(await page.locator('#learning-total').innerText(),'2');
    assert.equal(await page.locator('#demo-total').count(),0);
    assert.equal(await page.locator('.dashboard-summary > div').count(),2);
    assert.ok(!/demo|fictional|fixture|official source|published/i.test(await page.locator('body').innerText()));
    const announcement=page.locator('#health-announcement');
    assert.equal(await announcement.getAttribute('href'),'https://www.pib.gov.in/PressReleasePage.aspx?PRID=2227422');
    assert.equal(await announcement.getAttribute('target'),'_blank');
    assert.ok((await page.locator('.reminder').innerText()).includes('13 Feb 2026'));
    assert.ok((await page.locator('.reminder').innerText()).includes('Ministry of Health'));
    await announcement.focus();assert.ok(await announcement.evaluate(el=>el===document.activeElement));
    pass('V8/V9 public interface has no demo classification and the reminder links a dated government announcement');
    await page.locator('#vaccination').click();await synchronized(page,0);
    assert.equal(await page.locator('#search').inputValue(),'');assert.equal(await page.locator('#cost').inputValue(),'all');
    await page.locator('#reset').click();await page.locator('[data-category="learning"]').click();await page.locator('#cost').selectOption('free');await synchronized(page,0);
    await page.locator('#reset').click();pass('Public vaccination/free filters show honest empty results where service or price is unconfirmed');
    await page.waitForFunction(()=>document.querySelectorAll('.leaflet-tile-loaded').length>0,{},{timeout:20000});
    assert.ok(await page.locator('.leaflet-control-attribution').innerText().then(t=>t.includes('OpenStreetMap')));
    pass('Leaflet loads deterministic tiles, attribution, four public providers, and dashboard totals');
    await page.locator('[data-center="medanta"]').click();
    assert.ok((await page.locator('#details').innerText()).includes('2026-10-10'));
    assert.ok((await page.locator('#details').innerText()).includes('Approximate area'));
    assert.equal(await page.locator('#details .detail-facts > div').filter({has:page.locator('dt').filter({hasText:/^Source$/})}).locator('a').getAttribute('href'),'https://www.medanta.org/contact-us');
    assert.ok(!/demo|fictional|fixture|official source|published/i.test(await page.locator('body').innerText()));
    pass('Published hospital details include address, contact, official source, checked date, and location precision');
    // Isolated fixture-only scenarios retain the original filter/inquiry contracts.
    const fixtures=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/centers.json'),'utf8'));
    const publicData=JSON.parse(fs.readFileSync(path.join(root,'frontend/centers.json'),'utf8'));
    page.setDataset([...publicData,...fixtures.map(c=>({...c,isDemo:false}))]);
    await page.reload();await page.waitForSelector('[data-center]');
    await page.locator('#search').fill('conflicting search');await page.locator('#search').press('Enter');await page.locator('#cost').selectOption('paid');
    await page.locator('#vaccination').click();await synchronized(page,2);
    assert.equal(await page.locator('#search').inputValue(),'');assert.equal(await page.locator('#cost').inputValue(),'all');
    await page.locator('[data-center="health-1"]').click();await page.locator('#inquiry').click();
    assert.ok((await page.locator('#inquiry-preview').innerText()).includes('childhood vaccination services'));
    pass('V1 vaccination banner clears conflicting filters and opens the contextual inquiry');
    await page.locator('#reset').click();await page.locator('[data-category="learning"]').click();await page.locator('#cost').selectOption('free');
    await synchronized(page,2);await page.locator('[data-pin="learning-1"]').click();await page.locator('#inquiry').click();
    assert.ok((await page.locator('#inquiry-preview').innerText()).includes('opening hours'));
    pass('V2 Learning + Free and geographic marker selection share details and general inquiry');
    await page.locator('#reset').click();await page.locator('#search').fill('READING');await page.locator('#search').press('Enter');await synchronized(page,2);
    await page.locator('[data-center="learning-1"]').click();await page.locator('#search').fill('unmatched-zzzzz');await page.locator('#search').press('Enter');await synchronized(page,0);
    assert.equal(await page.locator('#close-details').count(),0);assert.equal(await page.locator('.empty-results').count(),1);
    await page.locator('#empty-reset').click();await synchronized(page,10);
    pass('V3/V4 case-insensitive search, empty state, excluded selection, and reset');
    await page.locator('[data-center="health-3"]').click();
    assert.ok((await page.locator('#details').innerText()).includes('Contact not provided'));
    assert.ok((await page.locator('#details').innerText()).includes('Not confirmed'));
    await page.locator('#inquiry').press('Enter');assert.equal(await page.locator('#inquiry').getAttribute('aria-expanded'),'true');
    assert.ok(await page.locator('#inquiry').evaluate(el=>el===document.activeElement));
    await page.locator('#inquiry').press('Enter');await page.locator('#close-details').press('Enter');
    assert.ok(await page.locator('[data-center="health-3"]').evaluate(el=>el===document.activeElement));
    pass('V5 unknown fields, inquiry toggle, and close return useful keyboard focus');
    await page.locator('#vaccination').click();await page.locator('#cost').selectOption('free');await page.locator('#search').fill('little');await page.locator('#search').press('Enter');
    await page.locator('#tag').click();await synchronized(page,1);assert.equal(await page.locator('#cost').inputValue(),'free');assert.equal(await page.locator('#search').inputValue(),'little');
    assert.ok(await page.locator('#reset').evaluate(el=>el===document.activeElement));
    await page.locator('#reset').click();
    pass('V7 tag removal preserves other restrictions and restores focus');
    await page.locator('.skip-link').focus();await page.keyboard.press('Enter');
    assert.ok(await page.locator('#results').evaluate(el=>el===document.activeElement));
    await page.keyboard.press('Tab');assert.ok(await page.locator('[data-center="medanta"]').evaluate(el=>el===document.activeElement));
    await page.keyboard.press('Enter');await page.keyboard.press('Enter');
    assert.ok(await page.locator('[data-center="medanta"]').evaluate(el=>el===document.activeElement));
    await page.locator('#search').focus();await page.keyboard.type('Udayan');await page.locator('#search').press('Enter');await synchronized(page,2);
    await page.locator('[data-pin="udayan-dundahera"]').focus();await page.keyboard.press('Enter');
    assert.ok((await page.locator('#details').innerText()).includes('Community technology skills'));
    await page.locator('#close-details').press('Enter');
    await page.locator('[data-pin="udayan-dundahera"]').focus();await page.keyboard.press('Space');
    assert.ok((await page.locator('#details').innerText()).includes('Community technology skills'));
    pass('V6 keyboard skip link, typed search, Enter/Space marker selection, and close');
    await page.locator('#reset').click();await page.locator('[data-center="udayan-manesar"]').click();
    for (const width of [320,390,760,1024,1280]) {
      await page.setViewportSize({width,height:844});
      const dimensions=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
      assert.ok(dimensions.document<=dimensions.viewport,JSON.stringify(dimensions));
      report.widths.push(dimensions);

    }
    await page.emulateMedia({reducedMotion:'reduce'});await page.reload();await page.waitForSelector('[data-center]');
    assert.equal(await page.locator('.center-card').first().evaluate(el=>getComputedStyle(el).transitionDuration),'0s');
    assert.equal(await page.evaluate(()=>map.options.zoomAnimation),false);
    pass('V6 no horizontal overflow at 320/390/760/1024/1280 and reduced-motion disables CSS/map animation');
    const broken = await newTestPage();
    const failedSearch=route=>route.fulfill({status:503,json:{error:{message:'Provider database unavailable.'}}});
    await broken.route('**/api/search',failedSearch);
    await broken.goto(base);await broken.getByText('Unable to load center information',{exact:true}).waitFor();
    assert.equal(await broken.locator('[data-center]').count(),0);assert.equal(await broken.locator('[data-pin]').count(),0);
    assert.ok(await broken.locator('#retry-search').isVisible());
    await broken.unroute('**/api/search',failedSearch);await broken.reload();await broken.waitForSelector('[data-center]');await synchronized(broken,4);await broken.close();
    pass('V7 dataset failure produces readable error, no fabricated records, and recovers after reload');
    const noTiles = await newTestPage();
    await noTiles.route('https://tile.openstreetmap.org/**',route=>route.abort());
    await noTiles.goto(base);await noTiles.waitForSelector('[data-center]');
    await noTiles.waitForFunction(()=>!document.getElementById('map-status').hidden);
    await noTiles.locator('[data-center="artemis"]').click();assert.ok((await noTiles.locator('#details').innerText()).includes('Artemis Hospital'));
    await synchronized(noTiles,4);
    await noTiles.unroute('https://tile.openstreetmap.org/**');await noTiles.route('https://tile.openstreetmap.org/**',r=>r.fulfill({status:200,contentType:'image/png',body:pixel}));await noTiles.locator('#retry-map').click();
    await noTiles.waitForFunction(()=>document.querySelectorAll('.leaflet-tile-loaded').length>0,{},{timeout:20000});
    await noTiles.waitForFunction(()=>document.getElementById('map-status').hidden);
    await noTiles.close();pass('OSM tile failure preserves discovery/details and Retry recovers');
    const noLibrary = await newTestPage();
    await noLibrary.route('**/vendor/leaflet/leaflet.js',route=>route.abort());
    await noLibrary.goto(base);await noLibrary.waitForSelector('[data-center]');
    assert.ok((await noLibrary.locator('#map-status').innerText()).includes('Map library unavailable'));
    await noLibrary.locator('[data-center="medanta"]').click();assert.ok((await noLibrary.locator('#details').innerText()).includes('Medanta'));
    await noLibrary.close();pass('Unavailable Leaflet library preserves hospital/list/details');
    assert.deepEqual(report.consoleErrors,[]);pass('No application JavaScript errors during normal discovery');
    report.status='passed';
  } finally {
    fs.writeFileSync(path.join(output,'caregiving-integrated-results.json'),JSON.stringify(report,null,2)+'\n');
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
