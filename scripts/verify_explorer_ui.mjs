/** Replayable integration tests using the Codex CUA browser API; no new dependencies.
 * In a CUA session: import this module, then verifyExplorerUI(tab, browser).
 * Uses only visible DOM, accessibility locators and documented CUA interactions.
 */
export async function verifyExplorerUI(tab, browser, base = 'http://127.0.0.1:3000') {
  const p = tab.playwright;
  const viewport = await browser.capabilities.get('viewport');
  const checks = [];
  const assert = (value, message) => { if (!value) throw new Error(message); };
  const observe = () => tab.getAXState({ emit: false });
  const click = async (name) => { await p.getByRole('button', { name, exact: true }).click(); await observe(); };
  const waitVisible = async (locator) => {
    const deadline = Date.now()+30000;
    while (Date.now()<deadline) {
      if (await locator.count() > 0 && await locator.isVisible()) return;
      await observe();
    }
    throw new Error('Expected interface element did not become visible');
  };
  const waitData = () => waitVisible(p.getByText('Available local observations match this query.', { exact:false }).first());
  try {
    await viewport.set({ width: 1440, height: 1000 });
    if (await tab.url() === `${base}/explorer`) await tab.reload();
    else await tab.goto(`${base}/explorer`);
    await waitData();
    assert(await p.getByRole('button', { name: 'All available dates', exact: true }).getAttribute('aria-pressed') === 'true', 'Default must use all dates');
    assert(!new URL(await tab.url()).searchParams.has('radius'), 'Initial map must have no circle');
    assert(await p.locator('.leaflet-tooltip.cluster-count').count() > 0, 'Numbered server clusters must be visible');
    checks.push('initial Italy/all dates, no area, numbered clusters');

    await click('Custom date range');
    await p.getByLabel('From', { exact: true }).fill('1990-01-01');
    // CUA date fill updates the native control; a keyboard edit commits React's change.
    await p.getByLabel('From', { exact: true }).press('ArrowUp');
    await observe();
    await p.getByLabel('From', { exact: true }).press('ArrowDown');
    await observe();
    await p.getByLabel('To', { exact: true }).fill('1990-01-07');
    await p.getByLabel('To', { exact: true }).press('ArrowUp');
    await observe();
    await p.getByLabel('To', { exact: true }).press('ArrowDown');
    await observe();
    await waitVisible(p.getByText('No data available in the current local archive for this area and period', { exact: false }).first());
    assert(await p.locator('.leaflet-tooltip.cluster-count').count() === 0, 'Empty date filter must remove old markers');
    checks.push('empty historical dates remove stale markers');

    await click('Last 30 days');
    await p.getByLabel('Satellite instrument').selectOption('VIIRS');
    await observe();
    await waitData();
    await click('Draw / edit circle');
    assert(await p.locator('path.leaflet-interactive').first().evaluate(el => getComputedStyle(el).pointerEvents) === 'none', 'Markers must not intercept drawing');
    await tab.getScreenshot({ emit: false });
    const box = await p.locator('.leaflet-container').evaluate(el => { const r=el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; });
    await tab.click([box.x+box.w*.5, box.y+box.h*.48]);
    await observe();
    await tab.click([box.x+box.w*.54, box.y+box.h*.48]);
    await observe();
    const drawnRadius = Number(new URL(await tab.url()).searchParams.get('radius'));
    assert(drawnRadius > 0 && drawnRadius <= 500, 'Two clicks must create a valid circle');
    await p.getByLabel('Search radius', { exact: false }).fill('20');
    await observe();
    assert(new URL(await tab.url()).searchParams.get('radius') === '20', 'Circle radius must be editable');
    await click('Clear circle');
    assert(!new URL(await tab.url()).searchParams.has('radius'), 'Clear must remove circle');
    checks.push('draw above clusters, edit radius, clear circle');

    await p.getByLabel('Center latitude', { exact: true }).fill('40.7');
    await p.getByLabel('Center longitude', { exact: true }).fill('-74');
    await p.getByLabel('Search radius', { exact: false }).fill('25');
    await observe();
    await waitVisible(p.getByText('No data available in the current local archive for this area and period', { exact: false }).first());
    assert(await p.locator('.leaflet-tooltip.cluster-count').count() === 0, 'Foreign circle must not show Italy points');
    await click('Return to Italy');
    const returned = new URL(await tab.url()).searchParams;
    assert(!returned.has('radius') && returned.get('sensor') === 'VIIRS' && returned.get('period') === '30d', 'Italy return must clear area and preserve filters');
    checks.push('international empty archive, return preserves date/sensor filters');

    await click('All available dates');
    await p.getByLabel('Satellite instrument').selectOption('both');
    await observe();
    await click('Last 30 days');
    const explorerStart = new URL(await tab.url()).searchParams.get('start');
    const analysisLinks = p.getByRole('link', { name: 'Analyze candidate', exact: true });
    await waitVisible(analysisLinks.first());
    const first = new URL(await analysisLinks.first().getAttribute('href'), base).pathname;
    await click('Next');
    await waitVisible(analysisLinks.first());
    assert(new URL(await analysisLinks.first().getAttribute('href'), base).pathname !== first, 'Pagination must fetch different candidates');
    await click('Previous');
    await waitVisible(analysisLinks.first());
    await p.getByRole('button', { name: 'Show on map', exact: true }).first().click();
    await observe();
    await waitVisible(p.getByText('Selected candidate', { exact: false }).first());
    await analysisLinks.first().click();
    await observe();
    await waitVisible(p.getByText('Algorithmic candidate · not an official perimeter', { exact: true }));
    const eventURL = await tab.url();
    await waitVisible(p.getByRole('button', {name:'Analyze this territory',exact:true}));
    assert(await p.getByRole('button', {name:'Analyze this territory',exact:true}).isEnabled(), 'Real unrequested event must expose explicit acquisition action');
    assert(!await p.getByRole('button', {name:'1. Before Fire',exact:true}).isEnabled(), 'Missing pre-fire observations must disable the phase instead of inventing a frame');
    assert(!await p.getByRole('button', {name:'3. Immediate Post-Fire',exact:true}).isEnabled(), 'Missing post-fire observations must disable the phase');
    await p.getByRole('button', {name:'2. Fire Period',exact:true}).click();
    await observe();
    await waitVisible(p.getByText('No event-scoped observations yet.', {exact:false}).first());
    assert(await p.getByText('DEMO DATA', { exact: true }).count() === 0, 'Real candidate must not be labeled as demo');
    await tab.reload();
    await observe();
    await waitVisible(p.getByText('Algorithmic candidate · not an official perimeter', { exact: true }));
    assert(await tab.url() === eventURL, 'Direct event URL must survive refresh');
    checks.push('server pagination, map selection and stable direct event URL');
    checks.push('no automatic satellite download; missing real pre/post observations disable unavailable phases');

    await p.getByRole('link', { name: '← Fire Explorer', exact: true }).click();
    await observe();
    await click('Return to Italy');
    await viewport.set({ width: 390, height: 844 });
    await observe();
    const mobile = await p.evaluate(() => { const r=document.querySelector('.leaflet-container').getBoundingClientRect(); return {mapHeight:r.height,mapWidth:r.width,viewport:innerWidth,document:document.documentElement.scrollWidth}; });
    assert(mobile.mapHeight >= 480 && mobile.mapWidth > 300, 'Mobile map must have a definite usable height');
    assert(mobile.document <= mobile.viewport + 2, 'Mobile page must not overflow horizontally');
    checks.push('390×844 layout with usable map and no horizontal overflow');
    return { checks, drawnRadius, eventURL, mobile };
  } finally {
    await viewport.reset();
    await observe();
  }
}
