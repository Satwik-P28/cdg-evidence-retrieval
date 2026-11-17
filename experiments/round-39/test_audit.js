#!/usr/bin/env node
const assert=require('node:assert/strict');
const {audit}=require('./audit.js');
const long='This policy permits the system to store full source bytes.';
const d={rows:[{date:'2025-01-01',text:long+'\n'},{date:'2025-02-01',text:'This policy forbids the system to store full source bytes.\n'}]};
const r=audit(d);assert.equal(r.summary.total_line_observations,2);assert.equal(r.summary.near_pairs,1);
assert.equal(r.summary.paired_observations+r.summary.unpaired_observations,2);
assert.equal(r.summary.adversarial_total,6);
assert.ok(r.adversarial.some(x=>x.reason==='negation'&&x.would_skip_at_075));
assert.ok(r.adversarial.some(x=>x.reason==='date'&&x.would_skip_at_075));
console.log('Round 39: 6 checks passed');
