#!/usr/bin/env node
/** Round 38: pinned authentic GitHub revision membership test, Node.js 18+, no dependencies.
 * node temporal_bench.js uv_readme_revisions.json [results.json]
 * Gold-derived line membership. No factual truth or natural-language QA.
 */
const fs=require('node:fs');
function benchmark(data){
const utf8=s=>{let n=0;for(let i=0;i<s.length;i++){const c=s.charCodeAt(i);if(c<128)n++;else if(c<2048)n+=2;else if(c>=55296&&c<=56319){n+=4;i++;}else n+=3;}return n;};
const lines=s=>new Set(s.split(/\r?\n/).map(x=>x.trim()).filter(x=>x.length>=25&&x.length<=320&&x.split(/\s+/).length>=4));
const rows=data.rows,sets=rows.map(r=>lines(r.text)),newest=sets[sets.length-1],all=new Set(sets.flatMap(x=>[...x])),q=[];
for(let i=1;i<rows.length;i++){
const prior=sets[i-1],cur=sets[i];
for(const line of prior)if(!cur.has(line))q.push({line,kind:"removed",target:i-1,transition:i});
for(const line of cur)if(!prior.has(line))q.push({line,kind:"added",target:i,transition:i});
}
const counts={};
for(const kind of ["removed","added"]){const a=q.filter(x=>x.kind===kind);counts[kind]={n:a.length,asof:a.filter(x=>sets[x.target].has(x.line)).length,latest:a.filter(x=>newest.has(x.line)).length,any_history:a.filter(x=>all.has(x.line)).length};}
return {source:{repo:data.repo,path:data.path,revisions:rows.map(r=>({commit:r.commit,date:r.date,blob:r.blob,bytes:utf8(r.text)}))},metrics:{n_queries:q.length,counts,latest_correct:counts.added.latest+counts.removed.latest,asof_correct:counts.added.asof+counts.removed.asof,raw_snapshots_bytes:rows.reduce((v,x)=>v+utf8(x.text),0),distinct_trimmed_lines_bytes:utf8([...all].join("\n")),current_snapshot_bytes:utf8(rows[rows.length-1].text),revisions:rows.length,scope:"Gold-derived exact line membership from real commit snapshots; not natural-language QA, factual validity, or a latency measurement"},transitions:rows.slice(1).map((r,i)=>({date:r.date,added:q.filter(x=>x.transition===i+1&&x.kind==="added").length,removed:q.filter(x=>x.transition===i+1&&x.kind==="removed").length}))};
}
const input=process.argv[2];if(!input)throw Error('Specify a pinned revision JSON file');
const output=benchmark(JSON.parse(fs.readFileSync(input,'utf8')));
const serialized=JSON.stringify(output,null,2)+'\n';
if(process.argv[3])fs.writeFileSync(process.argv[3],serialized);else process.stdout.write(serialized);
