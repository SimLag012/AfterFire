// Real map and production API, with a new browser profile for each screen size.
import assert from 'node:assert/strict';
import {performance} from 'node:perf_hooks';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.AF_BROWSER_BASE||'http://127.0.0.1:3000';
const browser=await chromium.launch();
try{
  for(const width of [1440,390]){
    const page=await browser.newPage({viewport:{width,height:900}});
    const requests=[],errors=[];
    page.on('request',r=>{if(r.url().includes('/global/hotspots?')) requests.push(r.url());});
    page.on('pageerror',e=>errors.push(e.message));
    const start=performance.now();
    const received=page.waitForResponse(r=>r.url().includes('/global/hotspots?'),{timeout:90000});
    await page.goto(base+'/');
    const res=await received;
    assert.equal(res.status(),200,await res.text().then(s=>s.slice(0,150)));
    const data=await res.json();
    assert(data.detections.length>0 && !data.truncated,'Italy must provide a reusable, populated observation window');
    const cutoff = new Date(Date.now() - 30 * 86400000).toISOString().slice(0,10);
    assert(new URL(res.url()).searchParams.get('end_date') <= cutoff);
    assert(data.detections.every(row => row.acq_date <= cutoff));
    const marker=page.locator('.fire-detection-cluster').first();
    await marker.waitFor();
    const initialMs=Math.round(performance.now()-start);
    const seed=data.detections.find(d=>d.longitude>7 && d.longitude<18 && d.latitude>36 && d.latitude<46);
    assert(seed);
    const lon=seed.longitude,lat=seed.latitude;
    const target=new URL(base+'/');
    target.searchParams.set('map',[lon-.15,lat-.1,lon+.15,lat+.1].join(','));
    target.searchParams.set('z','9');
    const count=requests.length, warm=performance.now();
    await page.goto(target.href);
    const cached=page.locator('.explorer-map-status summary').filter({hasText:/cached/});
    await cached.waitFor();
    const firstCachedMs=Math.round(performance.now()-warm);
    const map=page.locator('.leaflet-container');
    const interactions=[];
    async function move(action){
      const previous=new URL(page.url()).searchParams.get('map');
      const tick=performance.now();
      await action();
      await page.waitForFunction(old=>new URLSearchParams(location.search).get('map')!==old,previous);
      await cached.waitFor();
      interactions.push(Math.round(performance.now()-tick));
    }
    for(const label of ['Zoom in','Zoom out']){
      await move(()=>page.getByRole('button',{name:label,exact:true}).click());
    }
    await map.focus();await move(()=>page.keyboard.press('ArrowRight'));
    await move(()=>page.keyboard.press('ArrowLeft'));
    await page.reload();
    await cached.waitFor();
    const narrowed=new URL(page.url());
    narrowed.searchParams.set('sensor',seed.instrument);
    narrowed.searchParams.set('start',seed.acq_date);
    narrowed.searchParams.set('end',seed.acq_date);
    await page.goto(narrowed.href);
    await cached.waitFor();
    assert.equal(requests.length,count,'Covered pan/zoom and reload should generate zero hotspot HTTP requests');
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({width,observations:data.total_detections,candidates:data.events.length,initialProfileMs:initialMs,persistedViewMs:firstCachedMs,interactionMs:interactions,subsetDate:seed.acq_date,subsetSensor:seed.instrument,initialHotspotRequests:count,coveredPanZoomRefreshRequests:requests.length-count,errors}));
    const today = new Date().toISOString().slice(0,10);
    await page.goto(base + '/?period=custom&start=' + today + '&end=' + today);
    await page.waitForFunction(day => new URLSearchParams(location.search).get('end') === day, cutoff);
    await page.reload();
    await page.waitForFunction(day => new URLSearchParams(location.search).get('end') === day, cutoff);
    assert(requests.every(url => new URL(url).searchParams.get('end_date') <= cutoff));
    await page.close();
  }
}finally{await browser.close();}
