// Opens one bounded Rhodes candidate intentionally in two independent tabs.
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.AF_BROWSER_BASE||'http://127.0.0.1:3000';
const browser=await chromium.launch();
try{
  const context=await browser.newContext();
  const api=context.request;
  const url=base+'/api/v1/global/hotspots?bbox=27.92,36.14,28.00,36.21&start_date=2023-07-20&end_date=2023-07-22&sensor=MODIS';
  const view=await api.get(url);
  assert(view.ok());
  const id=(await view.json()).events[0].id;
  assert((await api.post(base+'/api/v1/global/events/'+id+'/select')).ok());
  const status=async()=>await (await api.get(base+'/api/v1/events/'+id+'/analysis/status')).json();
  const before=await status();
  const pages=await Promise.all([context.newPage(),context.newPage()]);
  const starts=[],errors=[];
  for(const page of pages){
    page.on('pageerror',e=>errors.push(e.message));
    page.on('response',r=>{if(r.request().method()==='POST' && r.url().endsWith('/analysis')) starts.push(r.json());});
  }
  const started=performance.now();
  await Promise.all(pages.map(p=>p.goto(base+'/events/'+id)));
  await pages[0].getByText('Satellite Recovery Story',{exact:true}).waitFor();
  if(before.state==='not_requested'){
    for(let i=0;i<180 && !starts.length;i++) await new Promise(resolve=>setTimeout(resolve,500));
    assert(starts.length);
    await Promise.all(starts);
    await pages[1].reload();
  }
  for(const page of pages) await page.getByText(/Cached scientific analysis/).waitFor({timeout:360000});
  const published=await status();
  assert(published.result_available && published.id && published.attempts===Math.max(1,before.attempts||0));
  for(const response of await Promise.all(starts)) assert.equal(response.id,published.id);
  if(before.result_available) assert.equal(starts.length,0);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({event:id,before:before.state,after:published.state,job:published.id,attempts:published.attempts,requestsFromTwoTabs:starts.length,resultVisibleSeconds:(performance.now()-started)/1000,errors}));
}finally{await browser.close();}
