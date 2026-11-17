#!/usr/bin/env node
/** Round 39: Audit lexical revisions before promoting an edit to a temporal fact change.
 * Gold-free: similarity is an inspection-priority signal, not semantic correctness.
 * node audit.js uv_readme_revisions.json [results.json]
 */
const fs=require('node:fs');
function audit(d){
  const canonical=s=>s.toLowerCase().replace(/https?:\/\/\S+/g," URL ").replace(/[`*_#\[\]()!|>]/g," ").replace(/\s+/g," ").trim();
  const tokenSet=s=>new Set(canonical(s).split(/\s+/).filter(Boolean));
  const similarity=(a,b)=>{const x=tokenSet(a),y=tokenSet(b),n=new Set([...x,...y]).size;return n?[...x].filter(z=>y.has(z)).length/n:1;};
  const selected=s=>new Set(s.split(/\r?\n/).map(x=>x.trim()).filter(x=>x.length>=25&&x.length<=320&&x.split(/\s+/).length>=4));
  const pairs=[];const transitions=[];
  for(let i=1;i<d.rows.length;i++){
    const a=selected(d.rows[i-1].text),b=selected(d.rows[i].text),deleted=[...a].filter(x=>!b.has(x)),added=[...b].filter(x=>!a.has(x));
    const edges=[];for(let x=0;x<deleted.length;x++)for(let y=0;y<added.length;y++)edges.push({x,y,similarity:similarity(deleted[x],added[y])});
    edges.sort((p,q)=>q.similarity-p.similarity||p.x-q.x||p.y-q.y);
    const matchedA=new Set(),matchedB=new Set();const matched=[];
    for(const e of edges){if(e.similarity<.75)break;if(matchedA.has(e.x)||matchedB.has(e.y))continue;matchedA.add(e.x);matchedB.add(e.y);const old=deleted[e.x],newText=added[e.y];matched.push({old,new:newText,similarity:+e.similarity.toFixed(4),normalized_equal:canonical(old)===canonical(newText)});}
    pairs.push(...matched.map(x=>({...x,transition:i})));
    transitions.push({transition:i,date:d.rows[i].date,deleted:deleted.length,added:added.length,near_pairs:matched.length,exact_normalized_pairs:matched.filter(x=>x.normalized_equal).length,unmatched_deletions:deleted.length-matched.length,unmatched_additions:added.length-matched.length});
  }
  const adversarial=[
    {before:"The service is available to all users.",after:"The service is not available to all users.",reason:"negation"},
    {before:"The limit is 10,000 requests per day.",after:"The limit is 1,000 requests per day.",reason:"numeric"},
    {before:"This medication is safe for children aged 12.",after:"This medication is unsafe for children aged 12.",reason:"antonym"},
    {before:"Access was revoked on 12 May 2025.",after:"Access was revoked on 12 May 2026.",reason:"date"},
    {before:"The policy allows processing of private documents.",after:"The policy forbids processing of private documents.",reason:"modality"},
    {before:"The service never stores the full source document.",after:"The service stores the full source document.",reason:"negation"}
  ];
  const adversary=adversarial.map(x=>({...x,similarity:+similarity(x.before,x.after).toFixed(4),would_skip_at_075:similarity(x.before,x.after)>=.75}));
  return {source:"astral-sh/uv README 12 pinned GitHub revisions",policy:"one-to-one greedy pairing of adjacent removed/added lines at token Jaccard >=0.75; similarity is not semantic equivalence",transitions,summary:{revisions:d.rows.length,total_line_observations:transitions.reduce((n,x)=>n+x.added+x.deleted,0),near_pairs:pairs.length,paired_observations:pairs.length*2,normalized_equal_pairs:pairs.filter(x=>x.normalized_equal).length,unpaired_observations:transitions.reduce((n,x)=>n+x.unmatched_deletions+x.unmatched_additions,0),adversarial_high_similarity:adversary.filter(x=>x.would_skip_at_075).length,adversarial_total:adversary.length},adversarial:adversary,examples:pairs.slice(0,12),scope:"Real edits; similarity-based candidate classification only; no factual-change ground truth or external temporal QA labels"};
}
if(require.main===module){const source=process.argv[2];if(!source)throw Error('require pinned revision input');const data=audit(JSON.parse(fs.readFileSync(source,'utf8')));const out=JSON.stringify(data,null,2)+'\n';if(process.argv[3])fs.writeFileSync(process.argv[3],out);else process.stdout.write(out);}
module.exports={audit};
