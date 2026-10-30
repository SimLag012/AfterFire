/** Real NASA UI verification with the system Chromium; no mocked API/science. */
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE??'/home/simlag012/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs');
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH??'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const evidence={};
const event='event-4a728489ea44ea85eab6a978870e0b06';
const intelligence=()=>page.getByRole('region',{name:'Recovery Intelligence',exact:true});
async function tiles(){await page.waitForFunction(()=>[...document.querySelectorAll('.leaflet-container')].every(map=>[...map.querySelectorAll('img.leaflet-tile')].some(i=>i.complete&&i.naturalWidth>0)),null,{timeout:45000});}
async function raster(){await page.waitForFunction(()=>[...document.querySelectorAll('img.leaflet-image-layer')].some(i=>i.complete&&i.naturalWidth>0),null,{timeout:30000});}
try{
 await page.goto('http://localhost:3000/explorer?period=custom&start=2021-08-11&end=2021-08-12&lat=37.0143&lon=14.7734&radius=10&event='+event);
 await page.getByRole('link',{name:'Analyze candidate',exact:true}).click();
 assert(page.url().includes(event));
 await page.getByLabel('Observation date',{exact:true}).selectOption('2026-09-30',{timeout:90000});await raster();
 await intelligence().getByText('Latest supported anomaly',{exact:true}).waitFor({timeout:90000});
 await intelligence().getByRole('button',{name:'Recheck assessment cache',exact:true}).click();
 await intelligence().getByText('Assessment interval: 2019-08-11–2026-10-28',{exact:true}).waitFor({timeout:60000});
 await tiles();
 evidence.panel=await intelligence().innerText();
 await intelligence().locator('.leaflet-overlay-pane svg path').nth(375).waitFor({state:'attached',timeout:90000});await tiles();
 evidence.cells=await intelligence().locator('.leaflet-overlay-pane svg path').count();assert(evidence.cells>=376);
 await intelligence().locator('.leaflet-container').evaluate(el=>el.scrollIntoView({block:'center'}));
 await intelligence().locator('.leaflet-overlay-pane path.leaflet-interactive').nth(180).click();
 await page.getByRole('article',{name:'Selected recovery cell'}).waitFor();
 evidence.cell=await page.getByRole('article',{name:'Selected recovery cell'}).innerText();assert(evidence.cell.includes('baseline'));
 for(const layer of ['anomaly','persistence','trend','reliability']){
  await page.getByLabel('Recovery layer',{exact:true}).selectOption(layer);
  assert(await intelligence().locator('.leaflet-overlay-pane svg path').count()>=376);
 }
 await page.getByLabel('Recovery layer',{exact:true}).selectOption('anomaly');
 await page.getByLabel('Vegetation index',{exact:true}).selectOption('EVI');await raster();
 await intelligence().getByRole('heading',{name:'Recovery Intelligence · EVI',exact:true}).waitFor();
 await intelligence().locator('.leaflet-overlay-pane svg path').nth(375).waitFor({state:'attached',timeout:90000});await tiles();
 evidence.evi=await intelligence().innerText();
 await intelligence().scrollIntoViewIfNeeded();await intelligence().screenshot({path:'docs/phase5-intelligence-desktop.png'});
 await page.getByLabel('Observation date',{exact:true}).selectOption('2021-08-29');await raster();
 await page.waitForFunction(()=>document.querySelector('[aria-label="Recovery Intelligence"]')?.textContent.includes('Selected composite: 2021-08-29'));
 evidence.dateSynced=true;
 if(process.env.VERIFY_ASSESSMENT_WINDOW==='1'){
  await page.getByLabel('Assessment from',{exact:true}).fill('2022-01-01');
  await page.getByLabel('Assessment through',{exact:true}).fill('2023-12-31');
  await page.getByLabel('Recovery layer',{exact:true}).selectOption('persistence');
  await intelligence().getByRole('button',{name:'Recheck assessment cache',exact:true}).click();
  await intelligence().getByText(/^Assessment period: 2022-01-01–2023-12-31/).waitFor({timeout:180000});
  evidence.selectedWindow='2022-01-01–2023-12-31';
  await intelligence().locator('.leaflet-overlay-pane path[stroke="#ffdb87"]').first().waitFor({state:'attached',timeout:60000});
  await intelligence().locator('.leaflet-container').evaluate(el=>el.scrollIntoView({block:'center'}));
  await intelligence().locator('.leaflet-overlay-pane path.leaflet-interactive').nth(180).click();
  await page.getByRole('article',{name:'Selected recovery cell'}).waitFor();
  evidence.cellClickWithPersistentZones=true;
  await page.getByLabel('Assessment from',{exact:true}).fill('');
  await page.getByLabel('Assessment through',{exact:true}).fill('');
  await intelligence().getByRole('button',{name:'Recheck assessment cache',exact:true}).click();
  await intelligence().getByText(/^Assessment period: 2019-08-11–2026-10-28/).waitFor({timeout:60000});
  evidence.fullWindowRestoredFromCache=true;
  await page.getByLabel('Recovery layer',{exact:true}).selectOption('anomaly');
 }

 const preYears=page.getByLabel('Pre-event years',{exact:true});await preYears.fill('2');
 await page.getByLabel('Observations through',{exact:true}).fill('2026-10-28');
 await page.getByRole('button',{name:'Preview acquisition plan',exact:true}).click();
 await page.getByLabel('Planning status',{exact:true}).waitFor({timeout:10000});
 evidence.planning=await page.getByLabel('Planning status',{exact:true}).innerText();
 await page.reload();
 await page.getByLabel('Planning status',{exact:true}).waitFor({timeout:30000});
 evidence.planningAfterReload=await page.getByLabel('Planning status',{exact:true}).innerText();
 await page.getByLabel('Acquisition plan',{exact:true}).waitFor({timeout:240000});
 evidence.plan=await page.getByLabel('Acquisition plan',{exact:true}).innerText();
 await page.getByRole('link',{name:'Compare Recovery →',exact:true}).click();
 await page.getByRole('region',{name:'Compare Recovery',exact:true}).waitFor();
 const options=page.getByRole('region',{name:'Compare Recovery',exact:true}).locator('input[type="checkbox"]');
 await options.nth(1).waitFor({timeout:30000});
 // Select distinct event IDs, preferring the historical source over the recent negative control.
 const labels=await page.getByRole('region',{name:'Compare Recovery',exact:true}).locator('label').allTextContents();
 evidence.comparisonOptions=labels;
 const list=await (await page.request.get('http://localhost:3000/api/v1/recovery-assessments')).json();
 const chosen=[];const seen=new Set();
 for(const option of list){if(seen.has(option.event_id))continue;seen.add(option.event_id);chosen.push(option);if(chosen.length===3)break;}
 const historical=chosen.find(o=>o.event_id==='event-de3698dc41cec7c190a85fa55f460c46');
 const reference=list.find(o=>o.event_id===event&&!o.parameters?.post_start&&!o.parameters?.post_end);
 const other=historical??chosen.find(o=>o.event_id!==event);
 assert(reference&&other);
 await page.goto(`http://localhost:3000/compare?assessment=${reference.assessment_id}&assessment=${other.assessment_id}`);
 const comparison=page.getByRole('region',{name:'Compare Recovery',exact:true});
 await comparison.getByText(/· common horizon/).waitFor({timeout:60000});
 evidence.comparison=await comparison.innerText();
 assert(await comparison.locator('.recharts-line-curve').count()>=1||evidence.comparison.includes('insufficient data'));
 await comparison.scrollIntoViewIfNeeded();await page.screenshot({path:'docs/phase5-comparison-desktop.png'});
 await page.getByLabel('Comparison index',{exact:true}).selectOption('EVI');
 await comparison.getByText(/· common horizon/).waitFor();
 await page.reload();await comparison.getByText(/· common horizon/).waitFor({timeout:60000});evidence.comparisonReload=true;
 await page.goto('http://localhost:3000/events/'+event);
 await page.getByLabel('Observation date',{exact:true}).selectOption('2026-09-30',{timeout:60000});await raster();await tiles();
 await intelligence().locator('.leaflet-overlay-pane svg path').nth(375).waitFor({state:'attached',timeout:90000});
 await page.setViewportSize({width:390,height:844});
 await page.getByLabel('Recovery Anomaly Map',{exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:'docs/phase5-intelligence-mobile.png'});
 evidence.mobile=await page.evaluate(()=>({viewport:innerWidth,width:document.documentElement.scrollWidth}));
 assert(evidence.mobile.width<=evidence.mobile.viewport);
 evidence.errors=errors;assert.deepEqual(errors,[]);
 evidence.loadedSatelliteTiles=await page.locator('img.leaflet-tile').evaluateAll(imgs=>imgs.filter(i=>i.complete&&i.naturalWidth>0).length);assert(evidence.loadedSatelliteTiles>0);
 evidence.downloads=await intelligence().locator('a[href$="recovery.tif"]').count();assert(evidence.downloads>0);
 evidence.ok=true;
}finally{await fs.writeFile('docs/phase5-ui-verification.json',JSON.stringify(evidence,null,2));await browser.close();}
