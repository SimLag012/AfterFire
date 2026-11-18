"""Copy the real frontend into public-demo; patch transport/capabilities, not UI design.

The original frontend is never edited. Re-run after frontend changes, then export
public data and build the clone. clone-source.json records every source hash.
"""
from pathlib import Path
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'frontend'
CLONE=ROOT/'public-demo'


def patch(name,old,new):
    p=CLONE/name;s=p.read_text()
    if old not in s:raise RuntimeError(f'Original source changed; review static capability patch: {name}: {old[:60]}')
    p.write_text(s.replace(old,new))


def import_runtime(name,names,relative):
    p=CLONE/name;p.write_text(f"import {{ {names} }} from '{relative}';\n"+p.read_text())


def remove_stale_sources():
    """Remove only source copies owned by the previous preparation manifest."""
    manifest = CLONE / 'clone-source.json'
    if not manifest.is_file():
        return
    for name in json.loads(manifest.read_text()).get('source_files', {}):
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or not relative.parts or relative.parts[0] != 'src':
            raise ValueError('Invalid managed source path in clone manifest')
        target = CLONE / relative
        if not target.resolve().is_relative_to(CLONE.resolve()):
            raise ValueError('Managed source escapes clone directory')
        if not (SOURCE / relative).is_file() and target.is_file():
            target.unlink()


def main():
    CLONE.mkdir(exist_ok=True)
    remove_stale_sources()
    sources={}
    for source in (SOURCE/'src').rglob('*'):
        if not source.is_file():continue
        relative=source.relative_to(SOURCE);target=CLONE/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        sources[str(relative)]=hashlib.sha256(source.read_bytes()).hexdigest()
    for name in ['index.html','tailwind.config.js','postcss.config.js','tsconfig.json','package.json','package-lock.json']:
        shutil.copyfile(SOURCE/name,CLONE/name)
    package=json.loads((CLONE/'package.json').read_text());package['name']='afterfire-public-demo';package['scripts']={'dev':'vite --host 127.0.0.1 --port 4173','build':'tsc && vite build','preview':'vite preview --host 127.0.0.1 --port 4173 --strictPort'};package['engines']={'node':'22.x'}
    (CLONE/'package.json').write_text(json.dumps(package,indent=2)+'\n')
    lock=json.loads((CLONE/'package-lock.json').read_text());lock['name']=package['name'];lock['packages']['']['name']=package['name'];lock['packages']['']['engines']=package['engines'];(CLONE/'package-lock.json').write_text(json.dumps(lock,indent=2)+'\n')
    # The actual App, router, Explorer, maps, charts and CSS remain the original.
    name='src/main.tsx';import_runtime(name,'initializeDemo','./demo/runtime')
    patch(name,"ReactDOM.createRoot(document.getElementById('root')!).render(","initializeDemo().then(() => ReactDOM.createRoot(document.getElementById('root')!).render(")
    patch(name,'  </React.StrictMode>\n);', "  </React.StrictMode>\n)).catch(error => { document.getElementById('root')!.textContent = 'Public snapshot unavailable: ' + error.message; });")
    name='src/api/selectedObservations.ts'
    target=CLONE/name
    signature=next(line for line in target.read_text().splitlines() if line.startswith('export async function loadSelectedObservations('))
    signature=signature.replace('refine=false','_refine=false').replace('signal?:AbortSignal','_signal?:AbortSignal')
    target.write_text("import { staticObservations } from '../demo/runtime';\n\n"+signature+"\n  return staticObservations(boxes, filters);\n}\n")
    name='src/api/satellite.ts';import_runtime(name,'visualAsset','../demo/runtime')
    patch(name,'=> `/api/v1${eventPath(eventId)}/analysis/assets/${encodeURIComponent(jobId)}/${encodeURIComponent(name)}`', '=> visualAsset(eventId,jobId,name)')
    name='src/pages/ExplorerPage.tsx';import_runtime(name,'READ_ONLY_NOTICE','../demo/runtime')
    patch(name,'<span>AfterFire</span>', '<span title={READ_ONLY_NOTICE}>AfterFire</span>')
    patch(name,'<summary>{detections.length} online observations in', '<summary>PUBLIC DEMO · {detections.length} saved observations in')
    patch(name,'<option value="online">NASA FIRMS on demand</option>', '<option value="online">Published FIRMS subset</option>')
    patch(name,'NASA FIRMS on demand supports bounded areas and up to 7 selected days, subject to provider coverage and a backend key. The optional local archive may be empty; missing records do not establish absence of fire.', 'PUBLIC DEMO: only the exported authentic candidates and periods are available. Changing filters reads saved data; no NASA acquisition is performed. Missing records do not establish absence of fire.')
    patch(name,'Search © OpenStreetMap contributors / Photon (ODbL) · country extents © Natural Earth', 'Search: exported candidate locations only · original published place names')
    # Use the same original sidebar/search/candidate actions and map; no demo page.
    name='src/pages/EventAnalysisPage.tsx';import_runtime(name,'PUBLIC_DEMO, opticalAsset, hasEvent, scientificDownload','../demo/runtime')
    patch(name,"enabled:!!event && event.is_synthetic_demo", "enabled:!PUBLIC_DEMO && !!event && event.is_synthetic_demo")
    patch(name,'disabled={active||start.isPending}', 'disabled={PUBLIC_DEMO||active||start.isPending}')
    patch(name,'disabled={start.isPending}', 'disabled={PUBLIC_DEMO||start.isPending}')
    patch(name,'{result.high_resolution?.before && result.high_resolution?.after && <>', '{result.high_resolution?.before && result.high_resolution?.after && opticalAsset(eventId,result.high_resolution.before.id) && opticalAsset(eventId,result.high_resolution.after.id) && <>')
    patch(name,'src={`/api/v1/events/${encodeURIComponent(eventId)}/analysis/optical-preview?job_id=${encodeURIComponent(result.job_id)}&scene_id=${encodeURIComponent(scene.id)}`}', 'src={opticalAsset(eventId,scene.id)}')
    patch(name,'to={`/events/${encodeURIComponent(r.event_id)}`}', 'to={hasEvent(r.event_id)?`/events/${encodeURIComponent(r.event_id)}`:returnTo} title={hasEvent(r.event_id)?undefined:\'Recovery not exported; return to available candidates\'}')
    patch(name,'href={satelliteApi.asset(eventId,result!.job_id,asset.raster)}', 'href={undefined} aria-disabled="true" title="Native GeoTIFF is not included in this public snapshot"')
    patch(name,'<div ref={setDownloadSection}/>', '<div ref={setDownloadSection}/><a className="underline text-xs" href={scientificDownload(eventId)} download>Published scientific JSON</a>')
    name='src/components/analysis/RecoveryIntelligencePanel.tsx';import_runtime(name,'PUBLIC_DEMO','../../demo/runtime')
    patch(name,'enabled:missing &&', 'enabled:!PUBLIC_DEMO && missing &&')
    patch(name,"setJobId(sessionStorage.getItem('assessment:'+sourceJobId)||'')", "setJobId('')")
    patch(name,'disabled={busy||start.isPending}', 'disabled={PUBLIC_DEMO||busy||start.isPending}')
    patch(name,'{missing && !initialAssessment.isError', '{!PUBLIC_DEMO && missing && !initialAssessment.isError')
    patch(name,'    {data&&metric&&period&&<>', '    {missing&&<p>No Recovery Intelligence assessment is included for this source publication. New assessment computation is disabled in the public demo.</p>}\n    {data&&metric&&period&&<>')
    patch(name,'href={`/api/v1/events/${encodeURIComponent(eventId)}/recovery-assessment/assets/${data.job_id}/${a.name}`}', 'href={undefined} aria-disabled="true" title="Native GeoTIFF is not included in the public snapshot"')
    name='src/components/analysis/ReburnIntelligencePanel.tsx';import_runtime(name,'PUBLIC_DEMO','../../demo/runtime')
    patch(name,"useState(()=>{try{return localStorage", "useState(()=>{if(PUBLIC_DEMO)return '';try{return localStorage")
    patch(name,'disabled={preflight.isPending}', 'disabled={PUBLIC_DEMO||preflight.isPending}')
    patch(name,"disabled={request.isPending||active.has", "disabled={PUBLIC_DEMO||request.isPending||active.has")
    patch(name,'checked={acquire} onChange=', 'checked={acquire} disabled={PUBLIC_DEMO} onChange=')
    patch(name,'No history is published for this event. Open the acquisition settings to analyze cached observations or retrieve missing data.', 'No Reburn history is included for this candidate in the public snapshot. New analyses and acquisition are disabled.')
    name='src/components/fireActivity/FireActivityPanel.tsx';import_runtime(name,'staticRequest, manifest, READ_ONLY_NOTICE','../../demo/runtime')
    begin=(CLONE/name).read_text().index('  const r=await fetch(');end=(CLONE/name).read_text().index('\n}',begin)
    p=CLONE/name;s=p.read_text();s=s[:begin]+"  return staticRequest('/fire-activity'+url,{},body?'post':'get',body);"+s[end:];p.write_text(s)
    patch(name,'disabled={submitting||!bbox}', 'disabled={true} title={READ_ONLY_NOTICE}')
    patch(name,'disabled={busy||!status.data}', 'disabled={true} title={READ_ONLY_NOTICE}')
    patch(name,'disabled={sources.isFetching}', 'disabled={true} title={READ_ONLY_NOTICE}')
    patch(name,"href={`/api/v1/fire-activity/studies/${study}/export/${kind}`}", "href={kind==='metadata'?snapshot.data?.studies.find(s=>s.id===study)?.calendar:undefined} aria-disabled={kind!=='metadata'} title={kind==='metadata'?'Published calendar JSON':'CSV export requires the local application'}")
    patch(name,'  const location=useLocation();', "  const location=useLocation();\n  const snapshot=useQuery({queryKey:['public-snapshot'],queryFn:manifest});")
    patch(name,'History starts only when you choose Acquire history.', 'Only studies listed under Cached study are available in the public demo; new acquisition is disabled.')
    name='src/components/layout/Navbar.tsx';patch(name,'health ? firmsLabels[health.effective_status]', "health ? 'PUBLIC DEMO · saved data'")
    target=CLONE/name
    content=target.read_text()
    begin=content.index('const firmsLabels = {')
    end=content.index('};',begin)+2
    target.write_text(content[:begin]+content[end:])
    name='src/pages/DatasetsPage.tsx';import_runtime(name,'READ_ONLY_NOTICE','../demo/runtime')
    patch(name,"const firmsStatus = firms?.connected ? 'Connected'", "const firmsStatus = firms?.status==='static_snapshot' ? 'PUBLIC DEMO · saved observations' : firms?.connected ? 'Connected'")
    patch(name,'Imported Italy archive', 'Public demo archive · selected candidates')
    patch(name,'disabled={!selectedFile || uploading', 'title={READ_ONLY_NOTICE} disabled={true || !selectedFile || uploading')
    patch(name,'      <section className="field-section" aria-labelledby="product-catalog">', '      <p className="field-note">{READ_ONLY_NOTICE} <a className="field-link" href="/demo/manifest.json" download>Coverage and provenance manifest</a></p>\n      <section className="field-section" aria-labelledby="product-catalog">')
    name='src/components/analysis/ResourceDiagnostics.tsx';patch(name,'disabled={!token||query.isPending}', 'disabled={true} title="Administration is unavailable in the public demo"')
    name='src/pages/ReportPage.tsx';patch(name,"queryKey: ['report', areaId],", "queryKey: ['report', areaId], enabled: false,")
    patch(name,"queryKey: ['recovery', areaId],", "queryKey: ['recovery', areaId], enabled: false,")
    name='src/components/analysis/RecoveryComparisonPanel.tsx';import_runtime(name,'manifest','../../demo/runtime')
    patch(name,"  const data=result.data;", "  const data=result.data;\n  const snapshot=useQuery({queryKey:['public-snapshot'],queryFn:manifest});")
    patch(name,"disabled={!ids.includes(o.assessment_id)&&ids.length>=4}", "disabled={!snapshot.data?.comparisons.some(c=>c.assessment_ids.includes(o.assessment_id))||(!ids.includes(o.assessment_id)&&ids.length>=4)} title='Only previously published comparisons are available in this public snapshot'")
    # No alternative stylesheets are created. Report copied/unmodified/transport files.
    changed={name for name,sha in sources.items() if hashlib.sha256((CLONE/name).read_bytes()).hexdigest()!=sha}
    (CLONE/'clone-source.json').write_text(json.dumps({'source':'../frontend','source_files':sources,'adapted_files':sorted(changed),'identical_files':sorted(set(sources)-changed),'clone_files':{str(p.relative_to(CLONE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (CLONE/'src').rglob('*') if p.is_file()}},indent=2)+'\n')
    print(f'Copied {len(sources)} original frontend files; {len(changed)} transport/capability adaptations; all styles copied verbatim.')


if __name__=='__main__':main()
