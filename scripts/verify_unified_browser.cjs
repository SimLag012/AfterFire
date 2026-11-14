/** Integration checks against the local API and retained NASA records.
 * No API interception or historical acquisition. Playwright is installed separately. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.AFTERFIRE_PLAYWRIGHT_MODULE||'playwright');
const base=process.env.AFTERFIRE_TEST_URL||'http://127.0.0.1:3000';
const out=path.resolve(process.env.AFTERFIRE_BROWSER_EVIDENCE||'/tmp');
const eventId='global-730fd3db3b65e67698840df5cf924b77';
const study='f275a42e8ec934dfbaa1cc0934862d6207d1fd2ad6e25f901b7b94e5d24c0968';
const records=[],errors=[],posts=[];
(async()=>{
fs.mkdirSync(out,{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:process.env.AFTERFIRE_CHROMIUM_EXECUTABLE});
try{
 for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:width===1440?900:844},isMobile:width<500,hasTouch:width<500});page.setDefaultTimeout(30000);
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST'&&(/\/fire-activity\//.test(r.url())||/\/analysis(?:\?|$|\/)/.test(r.url())))posts.push(r.url());});
  const check=async name=>{assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,name+': overflow');records.push({width,test:name,url:page.url()});console.log('PASS',width,name);};
  const params=new URLSearchParams({source:'archive',start:'2026-07-16',end:'2026-07-16',period:'custom',territory:JSON.stringify([[[39.2,8.5],[39.5,8.8]]]),place:'Iglesias'});
  await page.goto(base+'/explorer?'+params);
  await page.getByRole('heading',{name:'Algorithmic candidate events',exact:true}).waitFor();await page.getByRole('heading',{name:'Hotspot calendar',exact:true}).waitFor();await page.locator('.leaflet-container').waitFor();
  assert.equal(await page.locator('.app-header').count(),0);assert.equal(await page.locator('.fire-activity-panel').count(),0);await check('explorer_candidates_and_loaded_calendar');
  await page.getByRole('link',{name:'Data & Sources',exact:true}).click();
  await page.getByRole('heading',{name:'Product catalog',exact:true}).waitFor();await page.getByText('Configure live NASA FIRMS queries',{exact:true}).click();await page.getByRole('link',{name:'NASA FIRMS MAP key',exact:true}).waitFor();await check('full_data_sources_and_api_configuration');
  if(width<500)await page.getByRole('button',{name:'Toggle menu',exact:true}).click();await page.getByRole('link',{name:'Explorer',exact:true}).click();await page.getByRole('button',{name:'Return to Iglesias',exact:true}).waitFor();await check('data_sources_return_preserves_area');
  const back='/explorer'+new URL(page.url()).search;
  const detail=await (await page.request.get(base+'/api/v1/events/'+eventId)).json();
  await page.goto(base+'/events/'+eventId+'?returnTo='+encodeURIComponent(back));
  await page.getByRole('region',{name:'Recovery Intelligence',exact:true}).waitFor();await page.getByRole('heading',{name:'Before / After',exact:true}).waitFor();await page.getByRole('heading',{name:'Reburn History & Recovery Gap',exact:true}).waitFor();
  const activity=page.getByRole('region',{name:'Candidate fire activity',exact:true});await activity.getByText(new RegExp('^'+detail.detections.length+' loaded observations')).waitFor();await check('authentic_candidate_calendar_and_recovery');
  await page.getByRole('button',{name:'Historical Fire Activity Calendar',exact:true}).click();await page.getByLabel('Cached study',{exact:true}).selectOption(study);
  await page.locator('button.activity-cell[aria-label^="2026-07:"]').click();await page.waitForFunction(()=>document.querySelector('.activity-detail h3')?.textContent.startsWith('2026-07'));
  const original=await (await page.request.get(base+'/api/v1/fire-activity/studies/'+study+'/months/2026-07')).json();
  await activity.getByText(new RegExp('^'+original.observations.length+' loaded observations')).waitFor();assert.equal(new URL(page.url()).searchParams.get('returnTo'),back);assert.equal(new URL(page.url()).searchParams.has('study'),false);await check('cached_historical_month_and_original_counts');
  await page.screenshot({path:path.join(out,'analysis-calendar-'+width+'.jpg'),type:'jpeg',quality:75});
  await page.getByRole('link',{name:/Fire Explorer$/}).first().click();await page.getByRole('button',{name:'Return to Iglesias',exact:true}).waitFor();assert.equal(new URL(page.url()).searchParams.get('territory'),params.get('territory'));await check('analysis_back_preserves_territory');
  if(width===1440){
   await page.goto(base+'/recovery?event='+eventId+'&assessment=preserve-id');await page.waitForURL(/\/events\/global-/);assert.equal(new URL(page.url()).searchParams.get('assessment'),'preserve-id');await check('legacy_recovery_redirect');
   await page.goto(base+'/explorer?sources=on');await page.getByRole('heading',{name:'Data & Sources',exact:true}).waitFor();await check('legacy_data_sources_redirect');
   const assessments=await(await page.request.get(base+'/api/v1/recovery-assessments')).json();const distinct=[...new Map(assessments.map(a=>[a.event_id,a])).values()].slice(0,2);assert.equal(distinct.length,2);
   await page.goto(base+'/compare?'+distinct.map(a=>'assessment='+encodeURIComponent(a.assessment_id)).join('&'));await page.getByRole('region',{name:'Compare Recovery',exact:true}).waitFor();assert.deepEqual(new URL(page.url()).searchParams.getAll('assessment'),distinct.map(a=>a.assessment_id));await check('legacy_saved_comparison_redirect');
  }
  await page.close();
 }
 assert.deepEqual(errors,[]);assert.deepEqual(posts,[]);
 fs.writeFileSync(path.join(out,'sync-browser-verification.json'),JSON.stringify({status:'passed',records,errors,scientificAcquisitionPosts:posts.length,scope:'Actual local API and retained NASA-backed candidate/study data. Read-only scientific results. UI regression, not calibration evidence.'},null,2));
}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
