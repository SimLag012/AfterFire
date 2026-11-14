import type { FireDetection, EventMapItem } from '../types';
import { loadObservations } from './observationCache';

// Split large selected rectangles to respect the existing NASA adapter's 30° limit.
// Camera movements never reach this function: its input is the selected territory.
export async function loadSelectedObservations(boxes:number[][],filters:{start_date:string;end_date:string;sensor?:string;satellite?:string},refine=false,signal?:AbortSignal) {
  const parts:number[][]=[];
  for(const [w,s,e,n] of boxes)for(let x=w;x<e;x+=30)for(let y=s;y<n;y+=30)parts.push([x,y,Math.min(x+30,e),Math.min(y+30,n)]);
  const detections=new Map<string,FireDetection>(),events=new Map<string,EventMapItem>();const messages=new Set<string>();let truncated=false;let loaded=0;let allCached=true;
  for(const box of parts){
    signal?.throwIfAborted();
    try {
      const result=await loadObservations({...filters,bbox:box.join(','),strict_bounds:true},refine,signal);
      for(const d of result.detections)detections.set(d.id,d);
      for(const e of result.events||[])events.set(e.id,e);
      truncated ||= result.truncated;allCached &&= result.coverage?.state==='cached';loaded++;
      if(result.coverage?.message)messages.add(result.coverage.message);
    }catch(error){if(signal?.aborted||!loaded)throw error;truncated=true;messages.add('Some selected windows are unavailable; loaded observations are retained.');break;}
  }
  return {detections:[...detections.values()],events:[...events.values()],total_detections:detections.size,total_events:events.size,truncated,
    coverage:{state:truncated?'partial':allCached?'cached':'available',message:[...messages].join(' · ')}};
}
