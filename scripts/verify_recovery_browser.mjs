/** Fixture-free recovery entry points, cell history and comparison on desktop/mobile. */
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.AF_BROWSER_BASE||'http://127.0.0.1:3000';
const output=process.env.AF_BROWSER_OUTPUT||'/tmp/afterfire-recovery-ux';
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const report={checked_at:new Date().toISOString(),views:[]};
try{
 for(const viewport of [{width:1440,height:1050},{width:390,height:844}]){
  const page=await browser.newPage({viewport});page.setDefaultTimeout(60000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const view={viewport};report.views.push(view);
  const overflow=()=>page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  await page.goto(base+'/');await page.getByRole('heading',{name:'Explore historical observations',exact:true}).waitFor();
  assert.equal(await page.getByText('Partial Recovery (64%)',{exact:true}).count(),0);
  assert.equal(await page.getByText('Recovery Quotient & Status Metric',{exact:true}).count(),0);
  view.home_overflow=await overflow();
  await page.getByRole('link',{name:'View Recovery Analysis',exact:true}).click();
  await page.getByRole('heading',{name:'Post-fire Recovery Stories',exact:true}).waitFor();
  await page.getByRole('link',{name:'Open Recovery Story',exact:true}).first().waitFor();
  view.library_events=await page.getByRole('link',{name:'Open Recovery Story',exact:true}).count();
  view.library_overflow=await overflow();
  // Exact published real Rhodes candidate; viewport changes legitimately change membership IDs.
  const event='global-d77c8ac8d89369a61e7125f78cfe2e76';
  await page.goto(base+'/events/'+event);
  await page.getByText(/Cached scientific analysis/).waitFor();
  await page.getByRole('button',{name:'3. Immediate Post-Fire',exact:true}).click();
  const trajectory=page.getByLabel('Observed vegetation and seasonal baseline',{exact:true});
  await trajectory.scrollIntoViewIfNeeded();
  await page.waitForFunction(()=>[...document.querySelectorAll('path.recharts-line-curve')].some(p=>p.getAttribute('name')==='NDVI'&&(p.getAttribute('d')||'').length>100));
  view.trajectory_rendered=true;
  await trajectory.screenshot({path:output+'-trajectory-'+viewport.width+'.png'});
  const panel=page.getByRole('region',{name:'Recovery Intelligence',exact:true});
  await panel.getByRole('button',{name:'Recheck assessment cache',exact:true}).waitFor();
  const paths=panel.locator('path.leaflet-interactive');await paths.first().waitFor();
  await paths.first().scrollIntoViewIfNeeded();await paths.first().click({force:true});
  const selected=page.getByRole('article',{name:'Selected recovery cell',exact:true});
  await selected.waitFor();await selected.getByLabel('Selected cell vegetation history',{exact:true}).waitFor();
  await selected.getByText('Observed dates, reference support and gaps',{exact:true}).click();
  assert(await selected.locator('tbody tr').count()>40);
  view.cell_rows=await selected.locator('tbody tr').count();
  view.cell_id=(await selected.getByRole('heading').innerText());
  const id=view.cell_id.match(/Native cell ([^ ]+)/)[1];
  const assessment=await page.request.get(base+'/api/v1/events/'+event+'/recovery-assessment/result');
  const result=await assessment.json();
  const cell=await (await page.request.get(base+'/api/v1/events/'+event+'/recovery-assessment/cells/'+encodeURIComponent(id)+'?index=NDVI&assessment_id='+result.job_id)).json();
  const firstRow=selected.locator('tbody tr').first();
  const point=cell.properties.series[0];
  assert((await firstRow.innerText()).includes(point.date));
  assert((await firstRow.innerText()).includes(point.value==null?'Unavailable':point.value.toFixed(4)));
  view.cell_api_matches_table=true;view.cell_overflow=await overflow();
  await selected.screenshot({path:output+'-selected-cell-'+viewport.width+'.png'});
  await page.screenshot({path:output+'-cell-'+viewport.width+'.png',fullPage:true});
  await panel.getByRole('link',{name:'Compare Recovery →',exact:true}).click();
  await page.getByRole('heading',{name:'Compare post-fire vegetation evidence',exact:true}).waitFor();
  const comparison=page.getByRole('region',{name:'Compare Recovery',exact:true});
  const checkboxes=comparison.getByRole('checkbox');await checkboxes.first().waitFor();
  const count=await checkboxes.count();assert(count>=2);
  for(let i=0;i<count;i++){if(await checkboxes.nth(i).isChecked())await checkboxes.nth(i).uncheck();}
  // The backend refuses comparing different parameterizations of the same event.
  const options=await (await page.request.get(base+'/api/v1/recovery-assessments')).json();
  const first=options.findIndex(o=>o.event_id===event);
  const second=options.findIndex(o=>o.event_id!==event&&o.name.includes('2020'));
  assert(first>=0&&second>=0);
  await checkboxes.nth(first).check();await checkboxes.nth(second).check();
  await comparison.getByText(/common horizon/).waitFor();
  assert.equal(await page.getByText('Recovery Status:',{exact:true}).count(),0);
  await page.getByLabel('Comparison index',{exact:true}).selectOption('EVI');
  await comparison.getByText(/common horizon/).waitFor();
  view.comparison_url=page.url();view.comparison_overflow=await overflow();
  await page.reload();await page.getByText(/common horizon/).waitFor();
  view.comparison_reload=true;
  await page.screenshot({path:output+'-compare-'+viewport.width+'.png',fullPage:true});
  view.errors=errors;
  assert(!errors.length&&!view.home_overflow&&!view.library_overflow&&!view.cell_overflow&&!view.comparison_overflow);
  await page.close();
 }
 await fs.writeFile(output+'.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}finally{await browser.close();}
