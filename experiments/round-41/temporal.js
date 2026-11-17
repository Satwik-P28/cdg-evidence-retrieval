#!/usr/bin/env node
'use strict';
/* Round 41: structural temporal lookup on PRISM-Edit's TimeConflict subset.
   This is gold-associated structured lookup, NOT open-domain retrieval, semantic verification, or independently sourced QA.
   Usage: node temporal.js <TimeConflict directory> [results.json] */
const fs=require('node:fs');
const path=require('node:path');
function parseCsv(s) {
 const out=[]; const re=/(?:^|\r?\n)(\d+),"((?:[^"]|"")*)"/g;let m;
 while((m=re.exec(s))!==null)out.push({id:Number(m[1]),qas:JSON.parse(m[2].replace(/""/g,'"'))});
 return out;
}
function asof(question) {
 const m=question.match(/\b(19\d{2}|20\d{2})\b/g);
 if(!m)return null;
 const month=question.match(/\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(19\d{2}|20\d{2})\b/i);
 if(month) {
  const months=['january','february','march','april','may','june','july','august','september','october','november','december'];
  const mon=months.indexOf(month[1].toLowerCase())+1;
  // Month-end chosen explicitly. This can infer more precision than the question establishes.
  const day=new Date(Date.UTC(Number(month[2]),mon,0)).getUTCDate();
  return {date:month[2]+'-'+String(mon).padStart(2,'0')+'-'+day,interpretation:'month_end'};
 }
 if(m.length>1) {const a=Number(m[0]),b=Number(m[1]);return {date:String(Math.floor((a+b)/2))+'-07-01',interpretation:'midpoint_between_years'};}
 return {date:m[0]+'-07-01',interpretation:'midyear'};
}
function interval(t) {
 const m=/^(\d{4}-\d\d-\d\d)\s+to\s+(\d{4}-\d\d-\d\d|\.\.\.)$/.exec(t);
 if(!m)throw Error('unparseable source interval '+t);
 return {start:m[1],end:m[2]==='...'?'9999-12-31':m[2]};
}
function matching(record,date){
 const found=[];
 for(const key of ['before','after']){const item=record[key+'_object'],v=interval(item.time_range);if(v.start<=date&&date<=v.end)found.push({key,label:item.label});}
 return found;
}
function evaluate(inputs){
 const aggregate={questions:0,legacy_latest_correct:0,temporal_correct:0,temporal_answered:0,abstained_none:0,abstained_ambiguous:0,bad_subject:0,parse_failure:0,by_relation:{},year_resolution:{},example_conflicts:[],source_interval_overlaps:0};
 for(const relation of ['P26','P35']){
  const raw=inputs['factual/'+relation],csv=inputs['text_factual/'+relation];
  const records=raw.trim().split(/\r?\n/).filter(Boolean).map(JSON.parse),qas=parseCsv(csv);
  const byId=new Map(records.map(r=>[r.id,r]));const relationStats={records:records.length,qa_rows:qas.length,questions:0,latest_correct:0,temporal_correct:0,temporal_answered:0,none:0,ambiguous:0};
  for(const q of qas){
   const source=byId.get(q.id);if(!source)throw Error('no id '+q.id);
   const subject=source.subject.label.toLowerCase();
   if(source.relation!==relation)throw Error('relation mismatch');
   for(const entry of q.qas){
    const actual=source[entry.type+'_object'];if(actual.label!==entry.answer)throw Error('gold answer mismatches corpus '+q.id);
    for(const question of entry.question){
     aggregate.questions++;relationStats.questions++;
     if(!question.toLowerCase().includes(subject)){aggregate.bad_subject++;continue;}
     const t=asof(question);if(!t){aggregate.parse_failure++;continue;}
     aggregate.year_resolution[t.interpretation]=(aggregate.year_resolution[t.interpretation]||0)+1;
     if(source.after_object.label===entry.answer){aggregate.legacy_latest_correct++;relationStats.latest_correct++;}
     const candidates=matching(source,t.date);
     if(candidates.length===0){aggregate.abstained_none++;relationStats.none++;}
     else if(candidates.length>1){aggregate.abstained_ambiguous++;relationStats.ambiguous++;
       if(aggregate.example_conflicts.length<8)aggregate.example_conflicts.push({relation,id:q.id,question,asof:t.date,candidates});}
     else {aggregate.temporal_answered++;relationStats.temporal_answered++;
      if(candidates[0].label===entry.answer){aggregate.temporal_correct++;relationStats.temporal_correct++;}
      else if(aggregate.example_conflicts.length<8)aggregate.example_conflicts.push({relation,id:q.id,question,asof:t.date,selected:candidates[0],expected:entry.answer});}
    }
   }
  }
  aggregate.by_relation[relation]=relationStats;
  for(const r of records){const a=interval(r.before_object.time_range),b=interval(r.after_object.time_range);if(a.start<=b.end&&b.start<=a.end)aggregate.source_interval_overlaps++;}
 }
 return {metrics:aggregate,contract:{question_time:'Month-year mapped to month end; year mapped to July 1; between-years mapped to midpoint July 1. These are modeling assumptions.',source_selection:'Gold-associated subject record and relation are given by the dataset row ID; not real question-to-document retrieval.',answer_labels:'Same dataset source constructs both structured facts and QA labels; NOT independently annotated answer verification.',time_semantics:'Dataset validity strings used as supplied, not externally audited.',conclusion:'Structural lookup diagnostic only. Reject cases with zero or multiple matching values.'}};
}
function readInputs(base){
 const r={};for(const rel of ['P26','P35']){
  r['factual/'+rel]=fs.readFileSync(path.join(base,'factual','conflicts_'+rel+'.jsonl'),'utf8');
  r['text_factual/'+rel]=fs.readFileSync(path.join(base,'text_factual','conflicts_'+rel+'.csv'),'utf8');
 }return r;
}
if(require.main===module){const input=process.argv[2];if(!input)throw Error('Require TimeConflict directory');
 const out=JSON.stringify(evaluate(readInputs(input)),null,2)+'\n';
 if(process.argv[3])fs.writeFileSync(process.argv[3],out);else process.stdout.write(out);}
module.exports={asof,interval,matching,evaluate,parseCsv};
