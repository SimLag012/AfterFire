import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
export default defineConfig(({command})=>{
 if(command==='build'){
  const provenance=JSON.parse(fs.readFileSync(path.resolve(__dirname,'clone-source.json'),'utf8'));
  for(const [name,sha] of Object.entries(provenance.clone_files)){
   if(createHash('sha256').update(fs.readFileSync(path.resolve(__dirname,name))).digest('hex')!==sha)throw new Error('Clone preparation is incomplete or source changed; run prepare_vercel_clone.py');
  }
  const root=path.resolve(__dirname,'public/demo');
  const m=JSON.parse(fs.readFileSync(path.join(root,'manifest.json'),'utf8'));
  if(m.schema!==1||m.mode!=='PUBLIC_DEMO'||!m.events?.length)throw new Error('Export authentic publications before building the clone');
  for(const [name,entry] of Object.entries(m.files) as [string,{bytes:number;sha256:string}][]){
   if(!/^objects\/[a-f0-9]{64}\.(?:json|geojson|png)(?:\.gz)?$/.test(name))throw new Error('Invalid snapshot object path');
   const data=fs.readFileSync(path.join(root,name));
   if(data.length!==entry.bytes||createHash('sha256').update(data).digest('hex')!==entry.sha256)throw new Error('Snapshot checksum mismatch: '+name);
  }
 }
 return {plugins:[react()],resolve:{alias:{'@':path.resolve(__dirname,'src')}},server:{host:'127.0.0.1',port:4173,strictPort:true},preview:{host:'127.0.0.1',port:4173,strictPort:true}};
});
