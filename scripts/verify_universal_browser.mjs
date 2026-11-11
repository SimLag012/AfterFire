/** Live Explorer selection and event review; no API stubs or fixture images. */
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.AFTERFIRE_PLAYWRIGHT_MODULE || 'playwright');
const browser=await chromium.launch({...(process.env.AFTERFIRE_CHROMIUM_PATH?{executablePath:process.env.AFTERFIRE_CHROMIUM_PATH}:{}),headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[],failures=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('response',r=>{if(r.url().includes('/api/v1/')&&r.status()>=500)failures.push({url:new URL(r.url()).pathname,status:r.status()});});
const manifest=JSON.parse(await fs.readFile('docs/universal-coverage/manifest.json','utf8'));
const results=JSON.parse(await fs.readFile('docs/universal-coverage/after.json','utf8'));
const regression=JSON.parse(await fs.readFile('docs/universal-coverage/legacy-regression-result.json','utf8'));
results.push({event_id:regression.event_id,support:regression.scientific_support,high_resolution:regression.high_resolution});
const evidence={cases:[],errors,api_failures:failures};
try {
 const viewport=manifest.viewports[0];
 await page.goto(`http://localhost:3000/explorer?period=custom&start=${viewport.start}&end=${viewport.end}&sensor=MODIS&map=${viewport.bbox}`);
 const first=manifest.cases[0].event.id;
 const selected=page.locator(`a[href^="/events/${first}"]`).first();
 await selected.waitFor({timeout:60000});
 await page.screenshot({path:'docs/universal-coverage/explorer-desktop.png',fullPage:true});
 await selected.click();
 await page.getByRole('heading',{name:'How did this territory change?',exact:true}).waitFor();
 evidence.explorer_selection=page.url();
 const optical=results.find(r=>r.high_resolution?.status==='vegetation_observed');
 const candidate=results.find(r=>r.support?.analysis_scope==='candidate_area_vegetation_analysis');
 const cases=[results[0],candidate,optical].filter((v,i,a)=>v&&a.findIndex(r=>r?.event_id===v.event_id)===i);
 for (const row of cases) {
  await page.goto(`http://localhost:3000/events/${row.event_id}`);
  await page.getByLabel('Scientific coverage',{exact:true}).waitFor({timeout:30000});
  assert((await page.getByLabel('Scientific coverage',{exact:true}).innerText()).length>100);
  await page.locator('#before-after').scrollIntoViewIfNeeded();
  const images=page.locator('#before-after img[alt^="Quality-screened"]');
  for(let i=0;i<await images.count();i++)await images.nth(i).evaluate(img=>img.loading='eager');
  if(await images.count())await page.waitForFunction(()=>[...document.querySelectorAll('#before-after img')].every(i=>i.complete&&i.naturalWidth>0),null,{timeout:90000});
  const desktop={overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),dated_previews:await images.count()};
  await page.screenshot({path:`docs/universal-coverage/${row.event_id}-desktop.png`,fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.reload();
  await page.getByLabel('Scientific coverage',{exact:true}).waitFor();
  const mobile={overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)};
  await page.screenshot({path:`docs/universal-coverage/${row.event_id}-mobile.png`,fullPage:true});
  evidence.cases.push({event_id:row.event_id,desktop,mobile});
  assert(!desktop.overflow&&!mobile.overflow,'Horizontal overflow');
  await page.setViewportSize({width:1440,height:1000});
 }
 assert(!errors.length&&!failures.length,JSON.stringify({errors,failures}));
} finally {
 await fs.writeFile('docs/universal-coverage/browser.json',JSON.stringify(evidence,null,2));
 await browser.close();
}
console.log(JSON.stringify(evidence));
