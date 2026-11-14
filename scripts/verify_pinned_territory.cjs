/** Real browser + actual place-search API. Hotspot fixtures test UI/query scoping,
 * not NASA completeness or scientific calibration. No provider downloads. */
const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.AFTERFIRE_PLAYWRIGHT_MODULE||'playwright');
const out=process.env.AFTERFIRE_BROWSER_EVIDENCE||'/tmp';
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.AFTERFIRE_CHROMIUM_EXECUTABLE});const results=[];
 try{
 for(const viewport of [{width:1440,height:900},{width:390,height:844}]){
  console.log('Checking viewport',viewport.width,viewport.height);
  const page=await browser.newPage({viewport,hasTouch:viewport.width<500,isMobile:viewport.width<500});const errors=[],requests=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/v1/global/hotspots?**',route=>{
   requests.push(new URL(route.request().url()).searchParams.get('bbox').split(',').map(Number));
   return route.fulfill({json:{detections:[{id:'canaries',latitude:28.3,longitude:-16.5},{id:'balearics',latitude:39.6,longitude:3},{id:'mainland',latitude:40,longitude:-3},{id:'outside',latitude:40,longitude:9}].map(d=>({...d,acq_date:'2020-08-01',acq_time:'1300',satellite:'Aqua',instrument:'MODIS',confidence_level:'nominal',dataset_name:'UI-only fixture',is_synthetic_demo:'false'})),events:[],truncated:false,coverage:{state:'available',message:'UI regression fixture, not NASA evidence'}}});
  });
  await page.goto('http://127.0.0.1:3000/explorer?start=2020-08-01&end=2020-08-01&period=custom');
  await page.getByRole('heading',{name:'Fire Activity Calendar',exact:true}).waitFor({state:viewport.width<500?'hidden':'visible'});
  await page.getByLabel('Search location or latitude, longitude').fill('spagna');
  const searchResponse=page.waitForResponse(r=>r.url().includes('/explorer/search?'));
  await page.getByRole('button',{name:'Search location',exact:true}).click();
  const search=await (await searchResponse).json();const country=search.results[0];
  assert(country.bbox[0]<-18&&country.bbox[1]<28&&country.bbox[2]>4&&country.bbox[3]>43,'Country extent omits part of Spain');
  await page.locator('.explorer-search-results button').first().click();
  await page.getByRole('button',{name:'Return to Spagna',exact:true}).waitFor();
  await page.waitForFunction(()=>[...document.querySelectorAll('.explorer-map-status summary')].some(e=>e.textContent.startsWith('3 online observations in the selected territory')));
  const territory=new URL(page.url()).searchParams.get('territory');const expected=country.bbox;
  const waitForWholeArea=()=>page.waitForFunction(area=>{const b=(new URLSearchParams(location.search).get('map')||'').split(',').map(Number);return b.length===4&&b[0]<=area[0]&&b[1]<=area[1]&&b[2]>=area[2]&&b[3]>=area[3];},expected,{timeout:7000});
  await waitForWholeArea();
  await page.getByRole('button',{name:'Save view',exact:true}).click();
  const selectedRequests=requests.filter(b=>b.every((v,i)=>Math.abs(v-expected[i])<1e-8));assert(selectedRequests.length>0,'Selected full bbox was not requested');
  await page.waitForTimeout(500);const count=requests.length;const before=new URL(page.url()).searchParams.get('map');const map=await page.locator('.leaflet-container').boundingBox();
  if(viewport.width<500){
   const session=await page.context().newCDPSession(page);const x=Math.round(map.x+map.width*.75),y=Math.round(map.y+map.height*.5);
   await session.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});
   for(let i=1;i<=12;i++)await session.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:Math.round(x-map.width*.5*i/12),y:y+10}]});
   await session.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  }else{
   await page.mouse.move(map.x+map.width*.7,map.y+map.height*.55);await page.mouse.down();await page.mouse.move(map.x+map.width*.15,map.y+map.height*.7,{steps:12});await page.mouse.up();
  }
  await page.waitForFunction(previous=>new URLSearchParams(location.search).get('map')!==previous,before,{timeout:7000});
  await page.waitForTimeout(350);
  assert.equal(new URL(page.url()).searchParams.get('territory'),territory);assert.equal(requests.length,count,'Pan started another hotspot acquisition');
  await page.getByRole('button',{name:'Zoom in',exact:true}).click();await page.waitForTimeout(700);assert.equal(requests.length,count,'Zoom changed hotspot query bounds');
  const panRequests=requests.length-count;
  await page.getByRole('button',{name:'Return to Spagna',exact:true}).click();await waitForWholeArea();await page.waitForTimeout(300);assert.equal(new URL(page.url()).searchParams.get('territory'),territory);
  await page.reload();await page.getByRole('button',{name:'Return to Spagna',exact:true}).waitFor();assert.equal(new URL(page.url()).searchParams.get('territory'),territory);
  await waitForWholeArea();
  const theme=await page.evaluate(()=>({paper:getComputedStyle(document.documentElement).getPropertyValue('--color-paper'),background:getComputedStyle(document.body).backgroundColor}));
  await page.getByRole('link',{name:'Data & Sources',exact:true}).click();await page.getByRole('heading',{name:'Data & Sources',exact:true}).waitFor();
  assert.deepEqual(await page.evaluate(()=>({paper:getComputedStyle(document.documentElement).getPropertyValue('--color-paper'),background:getComputedStyle(document.body).backgroundColor})),theme);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  if(viewport.width<500)await page.getByRole('button',{name:'Toggle menu',exact:true}).click();
  await page.getByRole('link',{name:'Explorer',exact:true}).click();await page.getByRole('button',{name:'Return to Spagna',exact:true}).waitFor();assert.equal(new URL(page.url()).searchParams.get('territory'),territory);
  const beforeCoordinates=requests.length;
  await page.getByLabel('Search location or latitude, longitude').fill('35.6,139.7');
  await page.getByRole('button',{name:'Search location',exact:true}).click();
  await page.waitForFunction(()=>new URLSearchParams(location.search).get('place')==='35.6,139.7');
  await page.waitForTimeout(800);
  const small=requests.slice(beforeCoordinates);assert(small.length>0,'Small selected box was not acquired');
  const exact=[139.65,35.55,139.75,35.65];assert(small.every(b=>b.every((v,i)=>Math.abs(v-exact[i])<1e-8)),'A small selection was downloaded with an extra margin');
  await page.getByRole('button',{name:'Restore',exact:true}).click();
  await page.getByRole('button',{name:'Return to Spagna',exact:true}).waitFor();
  assert.equal(new URL(page.url()).searchParams.get('territory'),territory);
  await waitForWholeArea();
  assert.deepEqual(errors,[]);await page.screenshot({path:out+'/pinned-'+viewport.width+'.jpg',type:'jpeg',quality:80});
  results.push({viewport,status:'passed',selectedBoundingBox:expected,label:'Return to Spagna',panAndZoomRequests:panRequests,strictSmallBox:true,savedTerritoryRestored:true,theme,errors,scope:'Live Photon/Natural Earth search metadata; controlled hotspot fixtures.'});await page.close();
 }
 fs.writeFileSync(out+'/pinned-browser.json',JSON.stringify({status:'passed',results},null,2)+'\n');console.log(JSON.stringify(results));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
