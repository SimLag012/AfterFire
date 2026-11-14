/** Real-browser integration checks against the local API and retained NASA data.
 * Install Playwright separately; set AFTERFIRE_PLAYWRIGHT_MODULE and optionally
 * AFTERFIRE_CHROMIUM_EXECUTABLE. Never intercept or simulate API responses.
 */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.AFTERFIRE_PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.AFTERFIRE_TEST_URL || 'http://127.0.0.1:3000';
const out = path.resolve(process.env.AFTERFIRE_BROWSER_EVIDENCE || 'docs/unified-explorer');
const localStudy = 'f275a42e8ec934dfbaa1cc0934862d6207d1fd2ad6e25f901b7b94e5d24c0968';
const regionalStudy = 'fcff3f3165eb2317c1feffb937628338f256655967e790566c1b77d40eb78dac';
const records = [], errors = [], posts = [];
let browser;
const geometry = page => page.evaluate(() => {
  const rect = selector => document.querySelector(selector)?.getBoundingClientRect().toJSON();
  return {url:location.href,viewport:[innerWidth,innerHeight],map:rect('.leaflet-container'),
    calendar:rect('.fire-activity-panel'),overflow:document.documentElement.scrollWidth>innerWidth,
    bodyHeight:document.body.scrollHeight,nav:[...document.querySelectorAll('nav a')].map(e=>e.textContent)};
});
async function checkpoint(page, test, extra={}) {
  const result={test,...await geometry(page),...extra};
  assert.equal(result.overflow,false,`${test}: horizontal overflow`);
  records.push(result);console.log('PASS',test);
}
async function month(page, value) {
  await page.locator(`button.activity-cell[aria-label^="${value}:"]`).click();
  await page.waitForFunction(month=>document.querySelector('.activity-detail h3')?.textContent.startsWith(month),value);
}
async function eventFlow(page,label) {
  await page.getByLabel('Cached study',{exact:true}).selectOption(localStudy);
  await month(page,'2026-07');
  const selection=new URL(page.url()).searchParams;
  assert.equal(selection.get('radius'),'14.2');
  await checkpoint(page,label+'_authentic_month',{detail:(await page.locator('.activity-detail').innerText()).split('Compare month')[0]});
  await page.locator('.activity-detail a[href^="/events/global-730fd3db3b65e67698840df5cf924b77?"]').click();
  await page.getByRole('region',{name:'Recovery Intelligence',exact:true}).waitFor();
  await page.getByRole('heading',{name:'Before / After',exact:true}).waitFor();
  await page.getByRole('heading',{name:'Reburn History & Recovery Gap',exact:true}).waitFor();
  await checkpoint(page,label+'_recovery',{headings:await page.locator('h1,h2').allTextContents()});
  await page.screenshot({path:path.join(out,`sync-${label}-recovery.jpg`),type:'jpeg',quality:75});
  await page.getByRole('link',{name:/Fire Explorer$/}).first().click();
  await page.getByRole('heading',{name:'Fire Activity Calendar',exact:true}).waitFor();
  await page.waitForFunction(()=>document.querySelector('.activity-detail h3')?.textContent.startsWith('2026-07'));
  const returned=new URL(page.url()).searchParams;
  for(const key of ['study','month','lat','lon','radius'])assert.equal(returned.get(key),selection.get(key),`${label}: lost ${key}`);
  await checkpoint(page,label+'_return');
}
(async()=>{
  fs.mkdirSync(out,{recursive:true});
  browser=await chromium.launch({headless:true,...(process.env.AFTERFIRE_CHROMIUM_EXECUTABLE?{executablePath:process.env.AFTERFIRE_CHROMIUM_EXECUTABLE}:{})});
  const attach=page=>{
    page.setDefaultTimeout(20000);
    page.on('pageerror',e=>{errors.push({message:e.message,stack:e.stack,url:page.url(),lastCheckpoint:records.at(-1)?.test});console.error('PAGE ERROR',e.stack);});
    page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('/fire-activity/'))posts.push(r.url());});
  };
  const desktop=await browser.newPage({viewport:{width:1440,height:900}});attach(desktop);
  const initialStarted=Date.now();
  await desktop.goto(base);
  await desktop.getByRole('heading',{name:'Fire Activity Calendar',exact:true}).waitFor();
  await desktop.locator('.leaflet-container').waitFor();
  await desktop.locator('.leaflet-tile-loaded').first().waitFor();
  const initial=await geometry(desktop);
  assert(initial.map.width>600&&initial.map.height>450&&initial.calendar.width>=350);
  assert.deepEqual(initial.nav,[]);assert.equal(await desktop.locator('.app-header').count(),0);await desktop.getByRole('link',{name:'AfterFire Explorer',exact:true}).waitFor();assert.equal(posts.length,0);
  await checkpoint(desktop,'desktop_initial',{automaticActivityPosts:posts.length,timeToMapCalendarAndFirstTileMs:Date.now()-initialStarted,performance:await desktop.evaluate(()=>({navigation:performance.getEntriesByType('navigation')[0]?.toJSON(),jsHeapBytes:performance.memory?.usedJSHeapSize,scope:'Fresh browser context; local warmed backend; includes first real basemap tile, not a worst-case network benchmark.'}))});
  await desktop.screenshot({path:path.join(out,'sync-desktop.jpg'),type:'jpeg',quality:80});
  await desktop.getByRole('link',{name:'Data & Sources',exact:true}).click();
  await desktop.getByRole('heading',{name:'Data & Sources',exact:true}).waitFor();
  await desktop.getByRole('heading',{name:'Product catalog',exact:true}).waitFor();
  await desktop.getByText('Configure live NASA FIRMS queries',{exact:true}).click();
  await desktop.getByRole('link',{name:'NASA FIRMS MAP key',exact:true}).waitFor();
  assert.equal(await desktop.getByRole('dialog',{name:'Data & Sources'}).count(),0);
  await desktop.getByRole('link',{name:'Explorer',exact:true}).click();
  await desktop.getByRole('heading',{name:'Fire Activity Calendar',exact:true}).waitFor();
  await desktop.getByLabel('Cached study',{exact:true}).selectOption(regionalStudy);
  await month(desktop,'2019-01');
  await checkpoint(desktop,'desktop_anomaly',{detail:(await desktop.locator('.activity-detail').innerText()).split('Compare month')[0]});
  await month(desktop,'2024-08');
  await checkpoint(desktop,'desktop_month_changed');
  await eventFlow(desktop,'desktop');
  // Legacy links retain event and saved-comparison identifiers.
  await desktop.goto(base+'/recovery?event=global-730fd3db3b65e67698840df5cf924b77&assessment=preserve-this-id');
  await desktop.waitForURL(/\/events\/global-/);assert.equal(new URL(desktop.url()).searchParams.get('assessment'),'preserve-this-id');
  records.push({test:'legacy_event_redirect',url:desktop.url()});
  await desktop.goto(base+'/explorer?sources=on');await desktop.getByRole('heading',{name:'Data & Sources',exact:true}).waitFor();
  records.push({test:'legacy_sources_redirect',url:desktop.url()});
  const assessments=await (await desktop.request.get(base+'/api/v1/recovery-assessments')).json();
  const distinct=[...new Map(assessments.map(a=>[a.event_id,a])).values()].slice(0,2);
  assert.equal(distinct.length,2,'Two authentic saved assessments are required');
  await desktop.goto(base+'/compare?'+distinct.map(a=>'assessment='+encodeURIComponent(a.assessment_id)).join('&')+'&returnTo=%2Fexplorer');
  await desktop.waitForURL(/\/events\/global-/);
  await desktop.getByRole('region',{name:'Compare Recovery',exact:true}).waitFor();
  assert.deepEqual(new URL(desktop.url()).searchParams.getAll('assessment'),distinct.map(a=>a.assessment_id));
  records.push({test:'legacy_saved_assessment_redirect',url:desktop.url(),assessmentIds:distinct.map(a=>a.assessment_id)});
  const mobile=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:1});attach(mobile);
  await mobile.goto(base);
  await mobile.getByRole('button',{name:'Fire Activity Calendar',exact:true}).waitFor();
  assert.equal(await mobile.locator('.fire-activity-panel').count(),0);
  await checkpoint(mobile,'mobile_initial');
  assert.equal(await mobile.locator('.app-header').count(),0);
  await mobile.getByRole('link',{name:'AfterFire Explorer',exact:true}).waitFor();
  await mobile.getByRole('link',{name:'Data & Sources',exact:true}).waitFor();
  const calendarStarted=Date.now();
  await mobile.getByRole('button',{name:'Fire Activity Calendar',exact:true}).click();
  await mobile.getByRole('heading',{name:'Fire Activity Calendar',exact:true}).waitFor();
  await checkpoint(mobile,'mobile_one_tap_calendar',{openCalendarMs:Date.now()-calendarStarted});
  await mobile.screenshot({path:path.join(out,'sync-mobile-calendar.jpg'),type:'jpeg',quality:80});
  await mobile.getByRole('button',{name:'Close fire activity calendar'}).click();
  await mobile.getByRole('button',{name:'Fire data',exact:true}).click();
  await mobile.getByRole('button',{name:'Draw / edit circle',exact:true}).click();
  const box=await mobile.locator('.leaflet-container').boundingBox();
  const cdp=await mobile.context().newCDPSession(mobile);const x=Math.round(box.x+box.width*.5),y=Math.round(box.y+box.height*.6);
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});
  await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x+45,y:y+25}]});
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  await mobile.waitForFunction(()=>Number(new URLSearchParams(location.search).get('radius'))>0);
  await checkpoint(mobile,'mobile_touch_circle');
  await mobile.screenshot({path:path.join(out,'sync-mobile-circle.jpg'),type:'jpeg',quality:80});
  await mobile.getByRole('button',{name:'Fire Activity Calendar',exact:true}).click();
  await eventFlow(mobile,'mobile');
  const selectedBeforeSources=new URL(mobile.url()).searchParams;
  await mobile.getByRole('link',{name:'Data & Sources',exact:true}).click();
  await mobile.getByRole('heading',{name:'Data & Sources',exact:true}).waitFor();
  await mobile.getByRole('heading',{name:'Product catalog',exact:true}).waitFor();
  await checkpoint(mobile,'mobile_full_data_sources');
  await mobile.getByRole('button',{name:'Toggle menu'}).click();
  await mobile.getByRole('link',{name:'Explorer',exact:true}).click();
  await mobile.getByRole('heading',{name:'Fire Activity Calendar',exact:true}).waitFor();
  for(const key of ['study','month','lat','lon','radius'])assert.equal(new URL(mobile.url()).searchParams.get(key),selectedBeforeSources.get(key));
  await checkpoint(mobile,'mobile_sources_return');
  assert.equal(posts.length,0,'Read-only exploration initiated historical acquisition');
  assert.deepEqual(errors,[],'Browser JavaScript errors');
  fs.writeFileSync(path.join(out,'sync-browser-verification.json'),JSON.stringify({status:'passed',base,records,errors,activityPosts:posts.length,scope:'Production frontend and actual local NASA-backed API. Read-only cache, touch circle, calendar, anomaly, month, original event, Recovery and redirects. Fresh provider acquisition tested separately.'},null,2)+'\n');
})().catch(async e=>{
  console.error(e.stack);fs.writeFileSync(path.join(out,'sync-browser-verification.json'),JSON.stringify({status:'failed',error:e.message,records,errors},null,2)+'\n');process.exitCode=1;
}).finally(async()=>{await browser?.close();});
