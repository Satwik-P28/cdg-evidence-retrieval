#!/usr/bin/env node
'use strict';
/** Round 41: do not collapse a time-window query to a single day. */
const fs=require('node:fs'),path=require('node:path');
const {parseCsv,interval,matching,asof}=require('./temporal.js');
function temporalWindow(q){
 const month=q.match(/\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(19\d{2}|20\d{2})\b/i);
 if(month){const mm=['january','february','march','april','may','june','july','august','september','october','november','december'].indexOf(month[1].toLowerCase())+1,yy=Number(month[2]),last=new Date(Date.UTC(yy,mm,0)).getUTCDate();return {start:`${yy}-${String(mm).padStart(2,'0')}-01`,end:`${yy}-${String(mm).padStart(2,'0')}-${last}`,mode:"month"};}
 const ys=q.match(/\b(?:19|20)\d{2}\b/g);if(!ys)return null;
 if(ys.length>1){const yy=ys.map(Number);return {start:`${Math.min(...yy)}-01-01`,end:`${Math.max(...yy)}-12-31`,mode:"year_range"};}
 return {start:ys[0]+'-01-01',end:ys[0]+'-12-31',mode:"year"};
}
function strictMatch(record,win){
 const items=['before','after'].map(key=>({key,label:record[key+'_object'].label,...interval(record[key+'_object'].time_range)}));
 const touching=items.filter(x=>x.start<=win.end&&x.end>=win.start);
 const covering=touching.filter(x=>x.start<=win.start&&x.end>=win.end);
 if(covering.length===1&&touching.length===1)return {status:"answered",label:covering[0].label};
 return {status:touching.length===0?"no_applicable_source":"ambiguous_or_partially_valid",touching:touching.map(x=>x.key)};
}
function run(base){
 const out={total:0,point:{answered:0,correct:0,incorrect:0,abstain:0},interval:{answered:0,correct:0,incorrect:0,abstain:0},avoided_false_accepts:0,answered_by_relation:{},examples:[]};
 for(const rel of ['P26','P35']){
 const facts=fs.readFileSync(path.join(base,'factual','conflicts_'+rel+'.jsonl'),'utf8').trim().split(/\r?\n/).map(JSON.parse),by=new Map(facts.map(x=>[x.id,x]));
 const qas=parseCsv(fs.readFileSync(path.join(base,'text_factual','conflicts_'+rel+'.csv'),'utf8'));out.answered_by_relation[rel]={point:0,interval:0};
 for(const row of qas)for(const entry of row.qas)for(const question of entry.question){
  const fact=by.get(row.id),w=temporalWindow(question),point=matching(fact,asof(question).date),strict=strictMatch(fact,w);out.total++;const ok=point.length===1;
  if(ok){out.point.answered++;out.point[point[0].label===entry.answer?'correct':'incorrect']++;out.answered_by_relation[rel].point++;}else out.point.abstain++;
  if(strict.status==='answered'){out.interval.answered++;out.interval[strict.label===entry.answer?'correct':'incorrect']++;out.answered_by_relation[rel].interval++;}else out.interval.abstain++;
  if(ok&&point[0].label!==entry.answer&&strict.status!=='answered'){out.avoided_false_accepts++;if(out.examples.length<8)out.examples.push({rel,id:row.id,question,point:point[0].label,expected:entry.answer,window:w,strict:strict.status});}
 }
 }
 return out;
}
if(require.main===module){if(!process.argv[2])throw Error('Provide TimeConflict directory');const out=JSON.stringify(run(process.argv[2]),null,2)+'\n';if(process.argv[3])fs.writeFileSync(process.argv[3],out);else process.stdout.write(out);}
module.exports={temporalWindow,strictMatch,run};
