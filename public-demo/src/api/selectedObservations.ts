import { staticObservations } from '../demo/runtime';

export async function loadSelectedObservations(boxes:number[][],filters:{start_date:string;end_date:string;sensor?:string;satellite?:string},_refine=false,_signal?:AbortSignal) {
  return staticObservations(boxes, filters);
}
