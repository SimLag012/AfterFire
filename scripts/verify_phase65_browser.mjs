/** Real saved/lazy results and missing-product UI, desktop and mobile. */
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=await import('/home/simlag012/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs');
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const event='event-ed3e8c51a5e5d521edb70fefadd50287';
const page=await browser.newPage({viewport:{width:1440,height:1050}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
const evidence={};
try{
 const started=performance.now();await page.goto(`http://localhost:3000/events/${event}`);
 await page.getByText(/Cached scientific analysis/).waitFor();evidence.cached_visible_seconds=(performance.now()-started)/1000;
 const result=await (await page.request.get(`http://localhost:8000/api/v1/events/${event}/analysis/result`)).json();
 const observation=result.observations.find(o=>o.index==='NDVI'&&o.value!==null&&o.phase==='after');assert(observation);
 const before=performance.now();await page.getByLabel('Observation date',{exact:true}).selectOption(observation.date);
 await page.waitForFunction(()=>[...document.querySelectorAll('img.leaflet-image-layer')].some(i=>i.complete&&i.naturalWidth>0));
 evidence.lazy_frame_seconds=(performance.now()-before)/1000;
 evidence.desktop_overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 await page.screenshot({path:'docs/phase65-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.reload();await page.getByText(/Cached scientific analysis/).waitFor();
 evidence.mobile_overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 await page.screenshot({path:'docs/phase65-mobile.png',fullPage:true});
 evidence.errors=errors;assert(!evidence.desktop_overflow&&!evidence.mobile_overflow&&!errors.length);
 await fs.writeFile('docs/phase65-browser.json',JSON.stringify(evidence,null,2));console.log(evidence);
}finally{await browser.close();}
