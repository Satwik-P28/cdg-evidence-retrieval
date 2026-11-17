#!/usr/bin/env node
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const raw=fs.readFileSync(__dirname+'/temporal_bench.js','utf8');
const body=raw.slice(raw.indexOf('function benchmark('),raw.indexOf('const input=process.argv[2]'));
const run=vm.runInNewContext('('+body.trim()+')');
const d={repo:'toy',path:'toy',rows:[{commit:'a',date:'2025-01-01',blob:'x',text:'alpha beta gamma delta epsilon zeta\nshared common unchanged line in fixture\n'},{commit:'b',date:'2025-02-01',blob:'y',text:'newer beta gamma delta epsilon zeta\nshared common unchanged line in fixture\n'}]};
const r=run(d);assert.equal(r.metrics.n_queries,2);assert.equal(r.metrics.counts.removed.n,1);assert.equal(r.metrics.counts.added.n,1);assert.equal(r.metrics.asof_correct,2);assert.equal(r.metrics.latest_correct,1);console.log('Round 38 fixture checks passed');
