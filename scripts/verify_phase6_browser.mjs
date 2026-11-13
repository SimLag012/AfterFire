/** Real application/browser evidence; no mocked scientific responses. */
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=await import('/home/simlag012/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs');
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1050}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const event='event-4a728489ea44ea85eab6a978870e0b06';
const evidence={};
const requests=[];page.on('response',r=>{if(r.url().includes('/assets/'))requests.push({url:r.url(),status:r.status()});});
const panel=()=>page.getByRole('region',{name:'Reburn Intelligence',exact:true});
async function tiles(){await page.waitForFunction(()=>[...document.querySelectorAll('[aria-label="Spatial Reburn Map"] img.leaflet-tile')].some(i=>i.complete&&i.naturalWidth>0),null,{timeout:45000});}
try{
 await page.goto(`http://localhost:3000/explorer?period=custom&start=2021-08-11&end=2021-08-12&lat=37.0143&lon=14.7734&radius=10&event=${event}`);
 await page.getByRole('link',{name:'Analyze candidate',exact:true}).click();
 await panel().getByRole('heading',{name:'Reburn History & Recovery Gap',exact:true}).waitFor();
 // A bounded cached analysis makes no remote submission.
 await panel().getByText('History period and acquisition settings',{exact:true}).click();
 await page.getByLabel('Reburn history from',{exact:true}).fill('2021-07-01');
 await page.getByLabel('Reburn history through',{exact:true}).fill('2021-09-30');
 await panel().getByRole('button',{name:'Reburn preflight',exact:true}).click();
 await panel().getByText(/cached source candidates/).waitFor();
 const publicationResponse=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/reburn-analysis'));
 await panel().getByRole('button',{name:'Analyze cached history',exact:true}).click({timeout:240000});
 const requestedJob=(await (await publicationResponse).json()).id;
 await panel().getByText(/Published interval: 2021-07-01–2021-09-30/).waitFor({timeout:240000});
 await panel().locator('.leaflet-interactive').nth(93).waitFor({state:'attached'});await tiles();
 evidence.desktop=await panel().innerText();
 evidence.cells=await panel().locator('.leaflet-interactive').count();assert(evidence.cells===94);
 await panel().getByRole('button',{name:/Episode 1 ·/}).click();
 await page.getByLabel('Episode B',{exact:true}).selectOption({index:1});
 for(const layer of ['count','last','interval','gap','coverage']){
  await page.getByLabel('Reburn map layer',{exact:true}).selectOption(layer);
  assert(await panel().locator('.leaflet-interactive').count()===94);
 }
 await page.getByLabel('Reburn map layer',{exact:true}).selectOption('count');
 await panel().locator('[aria-label="Spatial Reburn Map"]').scrollIntoViewIfNeeded();
 await panel().locator('.leaflet-interactive').nth(35).click();
 await panel().getByRole('article',{name:'Selected reburn cell',exact:true}).waitFor();
 evidence.cell=await panel().getByRole('article',{name:'Selected reburn cell',exact:true}).innerText();
 assert(evidence.cell.includes('uncertainty bounds'));
 await page.getByLabel('Reburn vegetation index',{exact:true}).selectOption('EVI');
 await page.getByLabel('Reburn observation date',{exact:true}).selectOption('2021-08-29');
 await panel().getByText(/selected composite 2021-08-29/).waitFor();
 evidence.eviSynced=true;
 await panel().screenshot({path:'docs/phase6-reburn-desktop.png'});
 await page.getByRole('link',{name:'Open territory history',exact:true}).click();
 await panel().getByText(/Published interval:/).waitFor({timeout:60000});await tiles();
 const before=await panel().innerText();await page.reload();await panel().getByText(/Published interval:/).waitFor();await tiles();
 evidence.reloadPersisted=(await panel().innerText()).includes('Published interval:');assert(evidence.reloadPersisted);
 evidence.selectedJob=await page.evaluate(event=>localStorage.getItem('phase6:reburn:'+event),event);assert.equal(evidence.selectedJob,requestedJob);
 await page.setViewportSize({width:390,height:844});await page.reload();await panel().getByText(/Published interval:/).waitFor();await tiles();
 const overflow=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
 evidence.mobile=overflow;assert(overflow.scroll<=overflow.width+2,'Mobile horizontal page overflow');
 await panel().screenshot({path:'docs/phase6-reburn-mobile.png'});
 // Real cached-only missing-coverage case: zero means unknown, never an unburned claim.
 await page.goto(`http://localhost:3000/events/${event}/reburn`);
 await panel().getByText(/Published interval:/).waitFor({timeout:60000});
 await panel().getByText('History period and acquisition settings',{exact:true}).click();
 await page.getByLabel('Reburn history from',{exact:true}).fill('2020-01-01');
 await page.getByLabel('Reburn history through',{exact:true}).fill('2020-12-31');
 await panel().getByRole('button',{name:'Analyze cached history',exact:true}).click({timeout:240000});
 await panel().getByText(/Published interval: 2020-01-01–2020-12-31/).waitFor({timeout:240000});
 await panel().locator('.leaflet-interactive').nth(93).waitFor({state:'attached'});await tiles();
 evidence.noDataCells=await panel().locator('.leaflet-interactive').count();assert.equal(evidence.noDataCells,94);
 await page.getByLabel('Reburn burned cell',{exact:true}).selectOption({index:1});
 await panel().getByRole('article',{name:'Selected reburn cell',exact:true}).getByText('insufficient coverage',{exact:true}).waitFor();
 await panel().getByText('Insufficient spatial vegetation observations; no values are interpolated.',{exact:true}).waitFor();
 for(const missingLayer of ['count','last','gap']){
  await page.getByLabel('Reburn map layer',{exact:true}).selectOption(missingLayer);
  const fill=await panel().locator('.leaflet-interactive').nth(1).getAttribute('fill');
  assert(['#64748b','#94a3b8'].includes(fill),'Missing coverage must remain grey on every scientific layer');
 }
 evidence.noDataDistinguished=true;
 await panel().screenshot({path:'docs/phase6-nodata-mobile.png'});
 await page.goto('http://localhost:3000/recurrence');await page.getByRole('heading',{name:'Repeated Burning History',exact:true}).waitFor();
 evidence.recurrence=true;evidence.consoleErrors=errors;assert.deepEqual(errors,[]);evidence.assets=requests;
 await fs.writeFile('docs/phase6-browser-verification.json',JSON.stringify(evidence,null,2));
}finally{await browser.close();}
