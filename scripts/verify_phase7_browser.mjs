/** Real global explorer, selected-event API, maps and responsive UI; no API fixtures. */
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=await import('/home/simlag012/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs');
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1050}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
const evidence={};
try{
 await page.goto('http://localhost:3000/explorer?period=custom&start=2024-07-23&end=2024-07-25&sensor=MODIS&map=-118.2,52.75,-118.0,52.95');
 await page.waitForFunction(()=>document.querySelector('[aria-label="Fire data source"]')?.value==='online');
 await page.getByRole('link',{name:'Analyze candidate',exact:true}).first().waitFor();
 evidence.automatic_global_source=await page.getByLabel('Fire data source',{exact:true}).inputValue();
 evidence.global_candidate_links=await page.getByRole('link',{name:'Analyze candidate',exact:true}).count();
 await page.screenshot({path:'docs/phase7-explorer-desktop.png',fullPage:true});
 await page.getByRole('link',{name:'Analyze candidate',exact:true}).first().click();
 await page.getByRole('heading',{name:'Satellite Recovery Story',exact:true}).waitFor();evidence.selected_event_url=page.url();
 const r=JSON.parse(await fs.readFile('docs/phase7-analysis-Rhodes.json','utf8'));
 await page.goto(`http://localhost:3000/events/${r.event}`);await page.getByText(/Cached scientific analysis/).waitFor();
 await page.getByRole('button',{name:'3. Immediate Post-Fire',exact:true}).click();
 await page.waitForFunction(()=>[...document.querySelectorAll('img.leaflet-image-layer')].some(i=>i.complete&&i.naturalWidth>0));
 evidence.desktop_overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 await page.screenshot({path:'docs/phase7-science-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.reload();await page.getByText(/Cached scientific analysis/).waitFor();
 evidence.mobile_overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 await page.screenshot({path:'docs/phase7-science-mobile.png',fullPage:true});
 evidence.errors=errors;assert(!errors.length&&!evidence.desktop_overflow&&!evidence.mobile_overflow);
 await fs.writeFile('docs/phase7-browser.json',JSON.stringify(evidence,null,2));console.log(evidence);
}finally{await browser.close();}
