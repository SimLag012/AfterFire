/** Real published Chips/Dixie history; no mocked satellite responses. */
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.AF_BROWSER_BASE||'http://127.0.0.1:3000';
const output=process.env.AF_BROWSER_OUTPUT||'/tmp/afterfire-positive-reburn';
const event='global-51910cbfe4720638c1fce8630f452ce9';
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const report={checked_at:new Date().toISOString(),event,views:[]};
try{
 for(const viewport of [{width:1440,height:1050},{width:390,height:844}]){
  const page=await browser.newPage({viewport});page.setDefaultTimeout(60000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(r.url().includes('/api/v1/') && r.status()>=400) errors.push(r.status()+' '+new URL(r.url()).pathname);});
  await page.goto(base+'/events/'+event+'/reburn');
  await page.getByRole('heading',{name:'Reburn History & Recovery Gap',exact:true}).waitFor();
  await page.getByText('228 repeated cells · 48.94 km²',{exact:true}).waitFor();
  const published=await (await page.request.get(base+'/api/v1/events/'+event+'/reburn-analysis/result')).json();
  assert.equal(published.summary.repeated_cells,228);
  const evidence=published.supplemental_vegetation;
  assert.equal(evidence?.dates.length,251);
  assert.equal(evidence.result.classification,'supported_return_to_reference');
  const first=published.episodes.find(e=>e.id===evidence.result.episode_a);
  const second=published.episodes.find(e=>e.id===evidence.result.episode_b);
  const shared=first.cells.filter(id=>second.cells.includes(id)).sort();
  assert.deepEqual(shared,evidence.result.shared_cells.toSorted());
  assert.equal(shared.length,226);
  const selectB=page.getByLabel('Episode B',{exact:true});
  assert.equal(await selectB.inputValue(),second.id);
  await selectB.selectOption(published.episodes[1].id);
  await page.getByText('Two distinct episodes with shared observed cells are needed to assess the interval.').waitFor();
  await selectB.selectOption(second.id);
  const gap=page.getByRole('article',{name:'Recovery Gap',exact:true});
  await gap.getByText('226 shared burned cells',{exact:false}).waitFor();
  assert((await gap.innerText()).includes(first.start));
  assert((await gap.innerText()).includes(second.start));
  const validation=page.getByRole('region',{name:'Chips/Dixie vegetation validation'});
  await validation.getByText(/251 MOD13Q1.061 composites/).waitFor();
  for(const index of Object.keys(evidence.result.indices)) await validation.getByText('Observation support for '+index,{exact:true}).click();
  const rendered=await validation.innerText();
  for(const [index,metrics] of Object.entries(evidence.result.indices)){
   const last=metrics.last_pre_reburn;
   assert(rendered.includes(index));
   assert(rendered.includes(metrics.return_to_reference.start));
   assert(rendered.includes(last.value.toFixed(3))&&rendered.includes(last.baseline.toFixed(3)));
   assert(rendered.includes(last.valid_pixels+'/'+last.expected_pixels+' native pixels'));
  }
  await gap.getByText('Original burned-area job and uncertainty').click();
  await gap.getByText('insufficient observations',{exact:true}).waitFor();
  await validation.screenshot({path:output+'-vegetation-'+viewport.width+'.png'});
  const select=page.getByLabel('Reburn burned cell',{exact:true});
  await select.waitFor();
  const option=await select.locator('option').evaluateAll(es=>es.find(e=>e.textContent.includes('2 observed episodes'))?.value);
  assert(option);await select.selectOption(option);
  const cell=page.getByRole('article',{name:'Selected reburn cell',exact:true});await cell.waitFor();
  assert((await cell.innerText()).includes('2012-'));assert((await cell.innerText()).includes('2021-'));
  await cell.screenshot({path:output+'-cell-'+viewport.width+'.png'});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  assert(!overflow&&!errors.length);
  report.views.push({viewport,repeated_cells:published.summary.repeated_cells,shared_gap_cells:226,original_gap:'insufficient_observations',supplemental_gap:evidence.result.classification,supplemental_composites:evidence.dates.length,source_history:evidence.history_job,current_history:published.job_id,cell:option,overflow,errors});
  await page.close();
 }
 await fs.writeFile(output+'.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}finally{await browser.close();}
