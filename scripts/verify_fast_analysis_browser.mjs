import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=await import('/home/simlag012/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs');
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const event='event-4a728489ea44ea85eab6a978870e0b06';
const evidence={runs:[],errors:[]};
try{
 for(const viewport of [{width:1440,height:1050},{width:390,height:844}]){
  const page=await browser.newPage({viewport});
  const writes=[];page.on('pageerror',e=>evidence.errors.push(e.message));
  page.on('request',r=>{if(r.method()==='POST')writes.push(r.url());});
  const start=performance.now();
  await page.goto(`http://localhost:3000/events/${event}`);
  await page.getByText('Cached scientific analysis ·',{exact:false}).waitFor();
  const firstVisibleMs=performance.now()-start;
  assert.equal(writes.filter(u=>u.endsWith('/analysis')||u.includes('/analysis/preflight')).length,0);
  const before=await (await page.request.get(`http://localhost:3000/api/v1/events/${event}/analysis/status`)).json();
  const clicked=performance.now();
  const response=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/analysis'));
  await page.getByRole('button',{name:'Load saved analysis',exact:true}).click();
  const status=await (await response).json();
  await page.getByText('Cached scientific analysis ·',{exact:false}).waitFor();
  const clickMs=performance.now()-clicked;
  assert.equal(status.id,before.id);assert.equal(status.attempts,before.attempts);
  assert(['partial','completed'].includes(status.state));
  await page.reload();await page.getByText('Cached scientific analysis ·',{exact:false}).waitFor();
  assert.equal(writes.filter(u=>u.includes('/analysis/preflight')).length,0);
  assert.equal(writes.filter(u=>u.endsWith('/analysis')).length,1);
  await page.waitForFunction(()=>[...document.querySelectorAll('img.leaflet-tile')].some(i=>i.complete&&i.naturalWidth>0),null,{timeout:45000});
  await page.screenshot({path:`docs/fast-analysis-${viewport.width}.png`,fullPage:false});
  evidence.runs.push({viewport,firstVisibleMs,clickToSavedResultMs:clickMs,job:status.id,attempts:status.attempts,analysisPosts:1,preflightPosts:0});
  await page.close();
 }
 const fresh=await browser.newPage({viewport:{width:390,height:844}});
 const automatic=[];fresh.on('request',r=>{if(r.method()==='POST')automatic.push(r.url());});
 await fresh.goto('http://localhost:3000/events/event-0e53a2fe09462d51b10e79aa200ff875');
 await fresh.getByText('Last status received:',{exact:false}).waitFor();
 const status=await (await fresh.request.get('http://localhost:3000/api/v1/events/event-0e53a2fe09462d51b10e79aa200ff875/analysis/status')).json();
 await fresh.screenshot({path:'docs/fast-analysis-live-mobile.png',fullPage:false});
 assert.equal(automatic.filter(u=>u.endsWith('/analysis')||u.includes('/analysis/preflight')).length,0);
 evidence.existingRemoteTaskResume={state:status.state,phase:status.phase,workerHealth:status.worker_health,networkBytes:status.bytes_downloaded,automaticAnalysisPosts:0};
 await fresh.close();
 assert.deepEqual(evidence.errors,[]);
 await fs.writeFile('docs/fast-analysis-browser-verification.json',JSON.stringify(evidence,null,2));
 console.log(JSON.stringify(evidence,null,2));
}finally{await browser.close();}
