/** Real-browser verification. PLAYWRIGHT_MODULE may point to an installed Playwright package. */
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {inspectRecoveryStory} from './verify_phase4_ui.mjs';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH ?? '/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const evidence={};
const prefix=process.env.VERIFICATION_PREFIX??'phase4';
const url='http://localhost:3000/events/event-4a728489ea44ea85eab6a978870e0b06';
async function inspect() {
 await page.waitForFunction(()=>[...document.querySelectorAll('.leaflet-container')].every(map=>[...map.querySelectorAll('img.leaflet-tile')].some(i=>i.complete&&i.naturalWidth>0)),null,{timeout:30000});
 return inspectRecoveryStory({playwright:page});
}
async function frames(n) {
 await page.waitForFunction(n=>{const imgs=[...document.querySelectorAll('img.leaflet-image-layer')];return imgs.length===n&&imgs.every(i=>i.complete&&i.naturalWidth>0);},n,{timeout:30000});
}
try {
 await page.goto('http://localhost:3000/explorer?period=custom&start=2021-08-11&end=2021-08-12&lat=37.0143&lon=14.7734&radius=10&event=event-4a728489ea44ea85eab6a978870e0b06');
 await page.getByRole('link',{name:'Analyze candidate',exact:true}).click();
 assert(page.url().includes('/events/event-4a728489ea44ea85eab6a978870e0b06'));
 if(process.env.REPLAY_ANALYSIS==='1') {
 await page.getByLabel('Pre-event years',{exact:true}).fill('2');
 await page.getByLabel('Post-event years',{exact:true}).fill('10');
 await page.getByLabel('Observations through',{exact:true}).fill('2026-10-28');
 await page.getByRole('button',{name:'Preview acquisition plan',exact:true}).click();
 await page.getByLabel('Acquisition plan',{exact:true}).waitFor({timeout:120000});
 evidence.preflight=await page.getByLabel('Acquisition plan',{exact:true}).innerText();
 if(process.env.REPLAY_ANALYSIS==='1') await page.getByRole('button',{name:/^(Retry analysis|Analyze this territory)$/}).click();
 await page.getByLabel('Analysis Status',{exact:true}).getByText('Partial results — see quality notices · 100%',{exact:true}).waitFor({timeout:600000});
 evidence.publishedStatus=await page.getByLabel('Analysis Status',{exact:true}).innerText();
 }
 await page.getByLabel('Observation date',{exact:true}).selectOption('2021-07-28',{timeout:120000});await frames(3);
 evidence.before=await inspect();
 await page.getByLabel('Observation date',{exact:true}).selectOption('2026-09-30');await frames(3);
 evidence.after=await inspect();
 assert.notEqual(evidence.before.images.at(-1).source,evidence.after.images.at(-1).source);

 await page.getByLabel('Before observation',{exact:true}).selectOption('2021-07-12');
 await page.getByLabel('After observation',{exact:true}).selectOption('2026-09-30');await frames(3);
 evidence.desktop=await inspect();
 // Native HDF/subset envelopes can differ by empty boundary rows; one map fixes geographic projection.
 assert.equal(await page.getByLabel('Before After comparison',{exact:true}).locator('.leaflet-container').count(),1);
 const divider=page.getByLabel('Before After divider',{exact:true});await divider.focus();await divider.press('Home');
 evidence.clipStart=await inspect();await divider.press('End');evidence.clipEnd=await inspect();
 assert.notDeepEqual(evidence.clipStart.clipping,evidence.clipEnd.clipping);
 assert.deepEqual(evidence.clipStart.images.map(i=>i.bounds),evidence.clipEnd.images.map(i=>i.bounds));
 await divider.press('Home');await divider.press('ArrowRight');await divider.press('ArrowRight');await divider.press('ArrowRight');
 await divider.fill('50');
 await page.getByLabel('Before After comparison',{exact:true}).scrollIntoViewIfNeeded();
 await page.waitForTimeout(1500);await page.screenshot({path:`docs/${prefix}-before-after-desktop.png`});
 await page.getByLabel('Vegetation index',{exact:true}).selectOption('EVI');await frames(3);
 evidence.evi=await inspect();assert(evidence.evi.images.every(i=>i.source.includes('EVI')));
 // Click an actual plotted observation; chart -> single shared selected date.
 const point=page.locator('.recharts-line-dots circle').nth(12);await point.scrollIntoViewIfNeeded();await point.click({force:true});
 evidence.chartSelected=await page.getByLabel('Observation date',{exact:true}).inputValue();
 assert.notEqual(evidence.chartSelected,'2026-09-30');
 await page.getByLabel('Observation date',{exact:true}).selectOption('2019-12-03');
 await page.waitForFunction(()=>!document.querySelector('.leaflet-container img.leaflet-image-layer') || document.querySelectorAll('img.leaflet-image-layer').length===2);
 evidence.missing=await inspect();assert.equal(evidence.missing.images.length,2);

 await page.getByLabel('Observation date',{exact:true}).selectOption('2019-08-13');await frames(3);
 await page.getByLabel('Playback speed',{exact:true}).selectOption('4000');await page.getByRole('button',{name:'Play observations',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('[aria-label="Observation date"]').value!=='2019-08-13',null,{timeout:15000});
 await page.getByRole('button',{name:'Pause playback',exact:true}).click();
 evidence.playbackDate=await page.getByLabel('Observation date',{exact:true}).inputValue();
 await page.setViewportSize({width:390,height:844});
 await page.getByLabel('Observation date',{exact:true}).selectOption('2026-09-30');await frames(3);
 evidence.mobile=await inspect();assert.equal(evidence.mobile.overflow,false);
 await page.getByLabel('Before After comparison',{exact:true}).scrollIntoViewIfNeeded();
 await page.waitForTimeout(2000);await inspect();await page.screenshot({path:`docs/${prefix}-before-after-mobile.png`});
 await page.reload();await page.getByLabel('Observation date',{exact:true}).selectOption('2026-09-30');await frames(3);
 evidence.reload=await inspect();
 for(const k of ['desktop','evi','mobile','reload']){assert(evidence[k].tiles.loaded>0);assert(evidence[k].mapTiles.every(m=>m.loaded>0));assert(evidence[k].tiles.satelliteOnly);assert(evidence[k].images.every(i=>i.loaded));}
 assert.deepEqual(errors,[]);evidence.errors=errors;evidence.pass=true;
 await fs.writeFile(`docs/${prefix}-ui-verification.json`,JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence,null,2));
} finally {await browser.close();}
