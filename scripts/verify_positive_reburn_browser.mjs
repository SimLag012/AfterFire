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
  await page.goto(base+'/events/'+event+'/reburn');
  await page.getByRole('heading',{name:'Reburn History & Recovery Gap',exact:true}).waitFor();
  await page.getByText('228 repeated cells · 48.94 km²',{exact:true}).waitFor();
  const published=await (await page.request.get(base+'/api/v1/events/'+event+'/reburn-analysis/result')).json();
  assert.equal(published.summary.repeated_cells,228);
  await page.getByLabel('Episode B',{exact:true}).selectOption(published.episodes[2].id);
  const gap=page.getByRole('article',{name:'Recovery Gap',exact:true});
  await gap.getByText('insufficient observations',{exact:true}).waitFor();
  assert((await gap.innerText()).includes('common observed cells 226'));
  const select=page.getByLabel('Reburn burned cell',{exact:true});
  const option=await select.locator('option').evaluateAll(es=>es.find(e=>e.textContent.includes('2 observed episodes'))?.value);
  assert(option);await select.selectOption(option);
  const cell=page.getByRole('article',{name:'Selected reburn cell',exact:true});await cell.waitFor();
  assert((await cell.innerText()).includes('2012-'));assert((await cell.innerText()).includes('2021-'));
  await cell.screenshot({path:output+'-cell-'+viewport.width+'.png'});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  assert(!overflow&&!errors.length);
  report.views.push({viewport,repeated_cells:published.summary.repeated_cells,shared_gap_cells:226,gap:'insufficient_observations',cell:option,overflow,errors});
  await page.close();
 }
 await fs.writeFile(output+'.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}finally{await browser.close();}
