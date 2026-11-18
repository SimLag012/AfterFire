import { useMemo, useState } from 'react';
import type { FireDetection } from '../../types';
import './fireActivity.css';

/** A read-only calendar of exactly the records supplied to the observation map. */
export function ObservationCalendar({detections,scope,startDate,endDate,loading=false,unavailable=false,partial=false,description,id}:{detections:FireDetection[];scope:string;startDate:string;endDate:string;loading?:boolean;unavailable?:boolean;partial?:boolean;description?:string;id?:string}) {
  const [chosen,setChosen]=useState('');
  const counts=useMemo(()=>{
    const days=new Map<string,{total:number;modis:number;viirs:number}>();
    for(const d of detections){const row=days.get(d.acq_date)||{total:0,modis:0,viirs:0};row.total++;if(d.instrument==='MODIS')row.modis++;if(d.instrument==='VIIRS')row.viirs++;days.set(d.acq_date,row);}
    return days;
  },[detections]);
  const observedMonths=[...new Set([...counts.keys()].map(d=>d.slice(0,7)))].sort();
  const first=(startDate||observedMonths[0]||endDate||new Date().toISOString()).slice(0,7);
  const last=(endDate||observedMonths[observedMonths.length-1]||first).slice(0,7);
  const months:string[]=[];
  const cursor=new Date(first+'-01T00:00:00Z');
  // The supported satellite record is under 400 months; bound malformed input.
  while(Number.isFinite(cursor.getTime())&&cursor.toISOString().slice(0,7)<=last&&months.length<1200){months.push(cursor.toISOString().slice(0,7));cursor.setUTCMonth(cursor.getUTCMonth()+1);}
  if(!months.length)months.push(first);
  const month=months.includes(chosen)?chosen:months[0];
  const [year,number]=month.split('-').map(Number);
  const offset=(new Date(Date.UTC(year,number-1,1)).getUTCDay()+6)%7;
  const length=new Date(Date.UTC(year,number,0)).getUTCDate();
  return <section id={id} className="observation-calendar" aria-label="Hotspot calendar">
    <h2>Hotspot calendar</h2><p>{scope} · UTC</p>
    <p>{detections.length.toLocaleString()} loaded observations · {detections.filter(d=>d.instrument==='MODIS').length} MODIS · {detections.filter(d=>d.instrument==='VIIRS').length} VIIRS</p>
    {loading&&<p role="status">Updating observations…</p>}
    {unavailable&&<p role="alert">Observations unavailable for these filters. Calendar counts are unavailable.</p>}
    {partial&&<p role="status">Partial acquisition: counts include only loaded records.</p>}
    <label>Observation month <select aria-label="Observation month" value={month} onChange={e=>setChosen(e.target.value)}>{months.map(m=><option key={m}>{m}</option>)}</select></label>
    <div className="observation-days" role="table" aria-label={'Loaded hotspot observations · '+month}>
      {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(d=><span role="columnheader" key={d}>{d}</span>)}
      {Array.from({length:offset},(_,i)=><span key={'empty'+i} aria-hidden="true"/>)}
      {Array.from({length},(_,i)=>{const date=month+'-'+String(i+1).padStart(2,'0');const c=counts.get(date);const inRange=(!startDate||date>=startDate)&&(!endDate||date<=endDate);return <div role="cell" key={date} className={c?'has-observations':''} aria-label={`${date}: ${unavailable?'unavailable':!inRange?'outside selected dates':`${c?.total||0} loaded observations; ${c?.modis||0} MODIS; ${c?.viirs||0} VIIRS`}`} title={`${date} · MODIS ${c?.modis||0} · VIIRS ${c?.viirs||0}`}><span>{i+1}</span><strong>{unavailable||!inRange?'—':c?.total||0}</strong></div>;})}
    </div>
    <p>{description||'Counts describe the hotspots loaded for the map, not a fire count. Empty days do not establish absence of fire. Historical acquisition is available inside candidate analysis.'}</p>
  </section>;
}
