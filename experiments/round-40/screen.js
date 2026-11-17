#!/usr/bin/env node
'use strict';
/** Round 40: inspect authenticated historical source edits before costly verification.
 * Triage only. A citation change may require semantic escalation after its audit.
 * Usage: node screen.js uv_readme_revisions.json [results.json]
 */
const fs = require('node:fs');
function audit(data) {
  const included = s => new Set(s.split(/\r?\n/).map(x=>x.trim()).filter(x=>x.length>=25&&x.length<=320&&x.split(/\s+/).length>=4));
  const words = s => s.toLowerCase().replace(/https?:\/\/\S+/g, ' URL ').replace(/[`*_#\[\]()!|>]/g,' ').replace(/\s+/g,' ').trim().split(/\s+/).filter(Boolean);
  const similarity=(a,b)=>{const x=new Set(words(a)),y=new Set(words(b));return [...x].filter(t=>y.has(t)).length/new Set([...x,...y]).size;};
  const visible=s=>s.replace(/\[([^\]]+)\]\(([^)]+)\)/g,'$1').replace(/[`*_#>]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
  const links=s=>[...s.matchAll(/\[([^\]]+)\]\(([^)]+)\)/g)].map(x=>x[1]+' => '+x[2]);
  const sensitive=(a,b)=>{
    const re=/\b(?:not|never|no|without|except|only|all|none|some|any|may|must|shall|should|can|cannot|could|would|will|won't|does|doesn't|do|don't|is|isn't|are|aren't|allowed?|forbids?|permitted?|prohibited|safe|unsafe|before|after|until|from|through|more|less|over|under|\d[\d,.:%/-]*)\b/gi;
    const kw=s=>new Set((s.match(re)||[]).map(x=>x.toLowerCase()));
    const x=kw(visible(a)),y=kw(visible(b));
    return [...x].some(t=>!y.has(t))||[...y].some(t=>!x.has(t));
  };
  const classify=(a,b)=>{
    if(visible(a)!==visible(b))return 'semantic_review';
    if(JSON.stringify(links(a))!==JSON.stringify(links(b)))return 'citation_audit';
    return 'presentation_only';
  };
  const events=[];
  for(let i=1;i<data.rows.length;i++){
    const a=included(data.rows[i-1].text),b=included(data.rows[i].text);
    const deleted=[...a].filter(x=>!b.has(x)),added=[...b].filter(x=>!a.has(x));
    const edges=[];
    for(let j=0;j<deleted.length;j++)for(let k=0;k<added.length;k++)
      edges.push({j,k,score:similarity(deleted[j],added[k])});
    edges.sort((x,y)=>y.score-x.score||x.j-y.j||x.k-y.k);
    const usedA=new Set(),usedB=new Set();
    for(const e of edges){
      if(e.score<.75)break;
      if(usedA.has(e.j)||usedB.has(e.k))continue;
      usedA.add(e.j);usedB.add(e.k);
      const old=deleted[e.j],fresh=added[e.k];
      events.push({transition:i,type:'paired',before:old,after:fresh,similarity:+e.score.toFixed(4),
        classification:classify(old,fresh),critical_token_change:sensitive(old,fresh)});
    }
    for(let j=0;j<deleted.length;j++)if(!usedA.has(j))
      events.push({transition:i,type:'removed',before:deleted[j],after:null,classification:'semantic_review'});
    for(let j=0;j<added.length;j++)if(!usedB.has(j))
      events.push({transition:i,type:'added',before:null,after:added[j],classification:'semantic_review'});
  }
  const tally={events:events.length,paired:events.filter(x=>x.type==='paired').length,unpaired:events.filter(x=>x.type!=='paired').length,
    semantic:events.filter(x=>x.classification==='semantic_review').length,
    citation:events.filter(x=>x.classification==='citation_audit').length,
    presentation:events.filter(x=>x.classification==='presentation_only').length};
  const threats=[
    ['The service is available to all users.','The service is not available to all users.','negation'],
    ['The limit is 10,000 requests per day.','The limit is 1,000 requests per day.','number'],
    ['This medication is safe for children aged 12.','This medication is unsafe for children aged 12.','safety'],
    ['Access was revoked on 12 May 2025.','Access was revoked on 12 May 2026.','date'],
    ['The policy allows processing of private documents.','The policy forbids processing of private documents.','permissions'],
    ['The service never stores the full source document.','The service stores the full source document.','negation'],
    ['See the [security policy](https://example.org/original) for verification.','See the [security policy](https://example.org/attacker) for verification.','citation_redirect']
  ].map(([a,b,kind])=>({kind,classification:classify(a,b),critical_token_change:sensitive(a,b)}));
  const assumed={semantic:10,citation:2,screen_per_event:.1};
  const costs={assumptions:assumed,full_review:tally.events*10,skip_all_high_overlap:tally.unpaired*10,
    staged_review:tally.semantic*10+tally.citation*2+tally.events*.1,units:'abstract cost units, NOT measured latency'};
  return {source:{repo:'astral-sh/uv',revisions:data.rows.length},
    methods:{alignment:'one-to-one greedy token Jaccard>=0.75',safety:'No semantic labels; citation audit must escalate if source support changes'},
    tally,costs,adversarial:threats,matched:events.filter(x=>x.type==='paired'),
    limitations:['No independent semantic truth labels','No live LLM verifier or calibrated risk','Markdown reference-style links may be missed','Character/style changes could carry meaning','No measured decompression or wall-time cost']};
}
if(require.main===module){
  const input=process.argv[2];if(!input)throw Error('Require pinned revision JSON');
  const result=audit(JSON.parse(fs.readFileSync(input,'utf8')));
  const text=JSON.stringify(result,null,2)+'\n';
  if(process.argv[3])fs.writeFileSync(process.argv[3],text);else process.stdout.write(text);
}
module.exports={audit};
