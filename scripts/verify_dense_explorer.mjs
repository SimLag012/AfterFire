import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.AF_BROWSER_BASE||'http://127.0.0.1:3000';
const browser=await chromium.launch();
try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const requests=[],errors=[];
  page.on('request',r=>{if(r.url().includes('/global/hotspots?')) requests.push(r.url());});
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/explorer?start=2024-07-21&end=2024-07-27&sensor=VIIRS&map=-118.3,52.7,-117.9,53&z=9');
  const more=page.getByRole('button',{name:'Load more of this area'});
  await more.waitFor({timeout:90000});
  const count=async()=>Number((await page.locator('.explorer-map-status summary').textContent()).match(/(\d+) online observations/)[1]);
  const preview=await count();
  const before=requests.length;
  await more.click();
  await page.waitForFunction(()=>!document.querySelector('.explorer-map-status')?.textContent.includes('Updating satellite observations'),{},{timeout:180000});
  const after=await count();
  assert(after>=preview && requests.length>before && requests.length-before<=4);
  assert(requests.slice(before).every(url=>url!==requests[0]));
  await page.getByLabel('Search location or latitude, longitude').fill('Jasper');
  await page.getByRole('button',{name:'Search location',exact:true}).click();
  await page.locator('.explorer-search-results button').first().waitFor();
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({preview,after,newWindows:requests.length-before,moreAvailable:await more.isVisible(),locationResults:await page.locator('.explorer-search-results button').count(),errors}));
} finally{await browser.close();}
