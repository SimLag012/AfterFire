/** Replay in a CUA session with a bound event tab and browser; read-only DOM evidence. */
export async function inspectRecoveryStory(tab) {
  const p=tab.playwright;
  return {
    timeline: await p.getByRole('slider',{name:'Satellite timeline',exact:true}).count(),
    comparison: await p.getByRole('slider',{name:'Before After divider',exact:true}).count(),
    images: await p.locator('img.leaflet-image-layer').evaluateAll(images=>images.map(img=>({
      source:img.getAttribute('src'),loaded:img.complete&&img.naturalWidth>0,width:img.naturalWidth,
      bounds:{left:img.getBoundingClientRect().left,top:img.getBoundingClientRect().top,width:img.getBoundingClientRect().width,height:img.getBoundingClientRect().height},
    }))),
    tiles: await p.locator('img.leaflet-tile').evaluateAll(images=>({
      loaded:images.filter(img=>img.complete&&img.naturalWidth>0).length,
      satelliteOnly:images.every(img=>img.getAttribute('src')?.includes('/World_Imagery/MapServer/tile/')),
    })),
    mapTiles: await p.locator('.leaflet-container').evaluateAll(maps=>maps.map(map=>({
      loaded:[...map.querySelectorAll('img.leaflet-tile')].filter(img=>img.complete&&img.naturalWidth>0).length,
    }))),
    clipping: await p.locator('.leaflet-comparison-pane, .leaflet-comparison-before-pane').evaluateAll(panes=>panes.map(p=>getComputedStyle(p).clip)),
    overflow: await p.locator('body').evaluate(el=>el.scrollWidth>window.innerWidth),
    selected: await p.getByLabel('Observation date',{exact:true}).evaluate(el=>el.value),
    metric: await p.getByLabel('Vegetation index',{exact:true}).evaluate(el=>el.value),
  };
}
