// Browser regression for Italy overview bounds on desktop, mobile and a restored view.
import assert from 'node:assert/strict';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.AF_BROWSER_BASE || 'http://127.0.0.1:3000';
const browser = await chromium.launch({headless:true});
try {
  for (const [width, height, path] of [
    [1440, 900, '/'],
    [390, 844, '/'],
    [640, 640, '/?map=-1.05469%2C28.76766%2C26.27930%2C52.16045&z=4'],
  ]) {
    const page = await browser.newPage({viewport:{width,height}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const responsePromise = page.waitForResponse(r => r.url().includes('/global/hotspots?'), {timeout:90000});
    await page.goto(base + path);
    const response = await responsePromise;
    assert.equal(response.status(), 200);
    const data = await response.json();
    assert(data.total_detections > 0 && data.events.length > 0);
    const map = page.getByRole('region', {name:'Satellite observation map'});
    await map.getByText(new RegExp(data.total_detections + ' online observations')).waitFor();
    const tiles = map.locator('img.leaflet-tile-loaded');
    await tiles.first().waitFor();
    await map.locator('.fire-detection-cluster').first().waitFor();
    await page.waitForFunction(() => {
      const visible = [...document.querySelectorAll('.leaflet-tile-pane img')];
      return visible.length && visible.every(img => img.complete && img.naturalWidth > 0);
    });
    await page.screenshot({path:'/tmp/afterfire-entry-' + width + '.png'});
    const cluster = map.locator('.fire-detection-cluster').filter({hasText:/^[1-9]\d+$/}).first();
    await cluster.click();
    const popup = map.locator('.leaflet-popup-content');
    await popup.getByText(/clustered fire detections/).waitFor();
    await popup.locator('a[href^="/events/"]').first().click();
    await page.getByText('Satellite Recovery Story',{exact:true}).waitFor();
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({width,height,query:new URL(response.url()).searchParams.get('bbox'),observations:data.total_detections,candidates:data.events.length,event:page.url().split('?')[0]}));
    if (width === 1440) {
      await page.goto(base+'/about');
      await page.getByRole('link',{name:'Explore observations'}).filter({visible:true}).nth(1).click();
      const candidate = page.getByRole('link',{name:'Analyze candidate',exact:true}).first();
      await candidate.waitFor();
      const sensor = page.getByLabel('Satellite instrument');
      await sensor.selectOption('VIIRS');
      await candidate.waitFor();
      await page.getByLabel('Center latitude').fill('52.85');
      await page.getByLabel('Center longitude').fill('-118.1');
      await page.getByLabel(/Search radius/).fill('20');
      await page.getByText(/Circle: 52.8500/).waitFor();
      await candidate.waitFor();
      await page.getByRole('button',{name:'Clear circle'}).click();
      await candidate.waitFor();
      assert(!new URL(page.url()).searchParams.has('radius'));
      console.log('Jasper 2024 · VIIRS · editable 20 km circle · clear');
    }
    await page.close();
  }
} finally {
  await browser.close();
}
