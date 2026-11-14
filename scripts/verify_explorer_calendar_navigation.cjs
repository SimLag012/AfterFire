/** Controlled observation fixtures verify UI scoping/navigation, not NASA science.
 * Existing candidate analysis and historical study reads use the local API.
 * No acquisition or scientific publication is requested by this script. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {chromium}=require(process.env.AFTERFIRE_PLAYWRIGHT_MODULE||'playwright');
const base=process.env.AFTERFIRE_TEST_URL||'http://127.0.0.1:3000';
const out=process.env.AFTERFIRE_BROWSER_EVIDENCE||'/tmp';
const eventId='global-730fd3db3b65e67698840df5cf924b77';
const territory=JSON.stringify([[[27.4335426,-18.3936845],[43.9933088,4.5918885]]]);
const records=[],errors=[],posts=[];
const fixtures=[['mainland',40,-3,'2020-08-01','MODIS'],['nearby',40.01,-3,'2020-08-02','VIIRS'],['balearics',39.6,3,'2020-08-02','MODIS'],['canaries',28.3,-16.5,'2020-08-03','MODIS'],['outside',40,9,'2020-08-01','MODIS']].map(([id,latitude,longitude,acq_date,instrument])=>({id,latitude,longitude,acq_date,instrument,acq_time:'1300',satellite:instrument==='MODIS'?'Aqua':'S-NPP',candidate_event_id:eventId,confidence_level:'nominal',dataset_name:'Controlled UI fixture',is_synthetic_demo:'false'}));
const candidate={id:eventId,name:'UI candidate in Spain',place:'Spain',start_date:'2020-08-01',end_date:'2020-08-03',center_lat:40,center_lon:-3,min_lat:39.9,max_lat:40.1,min_lon:-3.1,max_lon:-2.9,detection_count:4,modis_detections:3,viirs_detections:1,confidence_summary:'UI fixture',detection_ids:fixtures.map(d=>d.id),sensors:['MODIS','VIIRS'],satellites:['Aqua','S-NPP'],is_synthetic_demo:'false'};
(async()=>{
fs.mkdirSync(out,{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:process.env.AFTERFIRE_CHROMIUM_EXECUTABLE});
try{
 for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:width===1440?900:844},hasTouch:width<500,isMobile:width<500});page.setDefaultTimeout(30000);
  const requests=[];
  page.on('pageerror',e=>{errors.push(e.message);console.error('PAGE ERROR',e.message);});
  page.on('request',r=>{if(r.method()==='POST')posts.push(r.url());});
  await page.route('**/api/v1/global/hotspots?**',r=>{requests.push(r.request().url());return r.fulfill({json:{detections:fixtures,events:[candidate],truncated:false,coverage:{state:'available',message:'Controlled UI fixture'}}});});
  const initial=new URLSearchParams({territory,place:'Spagna',start:'2020-08-01',end:'2020-08-03',period:'custom'});
  await page.goto(base+'/explorer?'+initial);
  const candidates=page.getByRole('heading',{name:'Algorithmic candidate events',exact:true});await candidates.waitFor();console.log('Checking viewport',width);
  const calendar=page.locator('.explorer-candidate-panel .observation-calendar');

  await calendar.getByText('4 loaded observations · 3 MODIS · 1 VIIRS',{exact:true}).waitFor();
  await calendar.getByRole('cell',{name:'2020-08-02: 2 loaded observations; 1 MODIS; 1 VIIRS',exact:true}).waitFor();
  assert.equal(await page.locator('.fire-activity-panel').count(),0,'Historical acquisition should be inside analysis');
  assert.equal(await page.getByRole('button',{name:'Fire data',exact:true}).getAttribute('aria-expanded'),'false');
  const geometry=await page.evaluate(()=>({map:document.querySelector('.leaflet-container').getBoundingClientRect().toJSON(),panel:document.querySelector('.explorer-candidate-panel').getBoundingClientRect().toJSON(),overflow:document.documentElement.scrollWidth>innerWidth}));
  assert.equal(geometry.overflow,false);assert(geometry.map.width>250&&geometry.map.height>250);assert(geometry.panel.height>120);
  await page.screenshot({path:out+'/calendar-'+width+'.jpg',type:'jpeg',quality:80});
  // Selecting a circle narrows both the records and their calendar without changing Spain.
  await page.getByRole('button',{name:'Fire data',exact:true}).click();
  await page.getByRole('button',{name:'Draw / edit circle',exact:true}).waitFor();
  await page.getByRole('button',{name:'Fire data',exact:true}).click();
  const circle=new URL(page.url());circle.searchParams.set('lat','40');circle.searchParams.set('lon','-3');circle.searchParams.set('radius','15');
  await page.goto(circle.toString());
  await calendar.getByText('2 loaded observations · 1 MODIS · 1 VIIRS',{exact:true}).waitFor();
  await calendar.getByRole('cell',{name:'2020-08-02: 1 loaded observations; 0 MODIS; 1 VIIRS',exact:true}).waitFor();
  await candidates.waitFor();assert.equal(new URL(page.url()).searchParams.get('territory'),territory);
  await page.getByRole('link',{name:'Analyze candidate',exact:true}).click();
  await page.getByRole('region',{name:'Candidate fire activity',exact:true}).waitFor();
  await page.getByRole('heading',{name:'Hotspot calendar',exact:true}).waitFor();
  await page.getByRole('button',{name:'Historical Fire Activity Calendar',exact:true}).click();
  await page.getByRole('heading',{name:'Fire Activity Calendar',exact:true}).waitFor();
  assert.equal(await page.locator('.fire-activity-panel').evaluate(el=>getComputedStyle(el).position),'static');
  // Reading a cached study must not change this candidate URL or the saved Explorer selection.
  const analysisUrl=page.url();
  const studies=await (await page.request.get(base+'/api/v1/fire-activity/studies')).json();
  if(studies.length){
   await page.getByLabel('Cached study',{exact:true}).selectOption(studies[0].id);
   await page.getByText(/Showing study area/).waitFor();
   assert.equal(page.url(),analysisUrl);
   assert.equal(new URLSearchParams(await page.evaluate(()=>localStorage.getItem('afterfire-last-explorer'))).get('territory'),territory);
  }
  // The global brand intentionally navigates to bare '/', exercising automatic restore.
  await page.getByRole('link',{name:'AfterFire',exact:true}).click();
  await page.getByRole('button',{name:'Return to Spagna',exact:true}).waitFor();
  await calendar.getByText('2 loaded observations · 1 MODIS · 1 VIIRS',{exact:true}).waitFor();
  let params=new URL(page.url()).searchParams;assert.equal(params.get('territory'),territory);assert.equal(params.get('radius'),'15');
  await page.goto(base+'/events/'+eventId);await page.getByRole('region',{name:'Candidate fire activity',exact:true}).waitFor();
  if(width<500)await page.getByRole('button',{name:'Toggle menu',exact:true}).click();
  await page.getByRole('link',{name:'Explorer',exact:true}).click();
  await page.getByRole('button',{name:'Return to Spagna',exact:true}).waitFor();assert.equal(new URL(page.url()).searchParams.get('territory'),territory);
  // A circle outside Spain must never request observations outside its pinned bbox.
  const outside=new URL(page.url());outside.searchParams.set('lat','40');outside.searchParams.set('lon','9');outside.searchParams.set('radius','15');
  const before=requests.length;await page.goto(outside.toString());
  await calendar.getByText('0 loaded observations · 0 MODIS · 0 VIIRS',{exact:true}).waitFor();assert.equal(requests.length,before);
  await page.getByRole('button',{name:'Return to Spagna',exact:true}).click();
  await calendar.getByText('4 loaded observations · 3 MODIS · 1 VIIRS',{exact:true}).waitFor();
  await page.reload();await page.getByRole('button',{name:'Return to Spagna',exact:true}).waitFor();await candidates.waitFor();
  await page.getByRole('button',{name:'Fire data',exact:true}).click();
  await page.getByRole('button',{name:'Draw / edit circle',exact:true}).click();
  const map=await page.locator('.leaflet-container').boundingBox();const x=Math.round(map.x+map.width*.5),y=Math.round(map.y+map.height*.5);
  if(width<500){
    const cdp=await page.context().newCDPSession(page);
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});
    await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x+18,y:y+10}]});
    await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  }else{await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+18,y+10,{steps:6});await page.mouse.up();}
  await page.waitForFunction(()=>Number(new URLSearchParams(location.search).get('radius'))>0);
  assert.equal(new URL(page.url()).searchParams.get('territory'),territory);await candidates.waitFor();await calendar.getByText('Selected circle · UTC',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Hotspot calendar',exact:true}).click();
  const title=await candidates.boundingBox(),pane=await page.locator('.explorer-candidate-panel').boundingBox();assert(title.y>=pane.y&&title.y+title.height<=pane.y+pane.height,'Candidates heading scrolled away');

  await calendar.scrollIntoViewIfNeeded();await page.screenshot({path:out+'/calendar-visible-'+width+'.jpg',type:'jpeg',quality:80});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.route('**/api/v1/explorer/hotspots?**',r=>r.fulfill({json:{detections:fixtures,truncated:true}}));
  await page.route('**/api/v1/explorer/events?**',r=>r.fulfill({json:{events:[candidate],total_events:1,total_detections:4,index_status:'ready'}}));
  const archive=new URLSearchParams(initial);archive.set('source','archive');await page.goto(base+'/explorer?'+archive);
  await calendar.getByText('4 loaded observations · 3 MODIS · 1 VIIRS',{exact:true}).waitFor();
  await calendar.getByText('Partial acquisition: counts include only loaded records.',{exact:true}).waitFor();await candidates.waitFor();
  assert.equal(await page.getByRole('button',{name:'Load more of this area',exact:true}).count(),0);
  // Explicit shared bbox wins over the automatic local last view.
  const shared=new URLSearchParams(initial);shared.set('source','archive');shared.set('territory',JSON.stringify([[[39.9,-3.1],[40.1,-2.9]]]));shared.set('place','Shared selection');
  await page.goto(base+'/explorer?'+shared);await page.getByRole('button',{name:'Return to Shared selection',exact:true}).waitFor();assert.equal(new URL(page.url()).searchParams.get('territory'),shared.get('territory'));
  records.push({width,status:'passed',fullAreaCount:4,circleCount:2,restoredBoundingBox:true,analysisCalendarInline:true,noOutsideAcquisition:true,geometry});await page.close();
 }
 assert.deepEqual(errors,[]);assert.deepEqual(posts.filter(url=>url.includes('/fire-activity/')||url.includes('/analysis')),[],'Viewing cached calendars must acquire no scientific data');
 fs.writeFileSync(out+'/calendar-navigation.json',JSON.stringify({status:'passed',records,errors,posts,scope:'Controlled hotspot fixtures plus real cached candidate/study API; UI checks, not scientific calibration evidence.'},null,2));console.log(JSON.stringify(records));
}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
