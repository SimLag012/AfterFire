import fs from 'node:fs/promises';
const {chromium}=await import('/home/simlag012/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs');
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
const page=await context.newPage();
const results=[];
for(const route of ['/','/explorer','/recurrence']){
 const start=performance.now();await page.goto('http://localhost:3000'+route);await page.waitForLoadState('networkidle');
 results.push({route,wallMs:performance.now()-start,...await page.evaluate(()=>({navigation:performance.getEntriesByType('navigation').map(n=>({domInteractive:n.domInteractive,domContentLoaded:n.domContentLoadedEventEnd,load:n.loadEventEnd})),resources:performance.getEntriesByType('resource').filter(r=>r.name.includes('/assets/')).map(r=>({name:r.name.split('/').pop(),transferBytes:r.transferSize,encodedBytes:r.encodedBodySize,durationMs:r.duration})),heap:performance.memory?{used:performance.memory.usedJSHeapSize,total:performance.memory.totalJSHeapSize}:null}))});
}
await fs.writeFile('docs/phase6-frontend-performance.json',JSON.stringify({conditions:'Headless system Chromium, localhost Docker Nginx, default network/CPU, same context sequential routes; first route cold browser cache. Wall times include network-idle wait. No comparable old browser-run timing captured.',routes:results},null,2));await browser.close();
