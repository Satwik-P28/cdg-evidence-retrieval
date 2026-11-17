#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {audit}=require('./screen.js');
function input(a,b){return {rows:[{text:a,date:'2025-01-01'},{text:b,date:'2025-02-01'}]};}
const a='- The service supports [all users](https://example.com/old) with daily usage limits.\n';
const b='- The service supports [all users](https://example.com/new) with daily usage limits.\n';
let r=audit(input(a,b));
assert.equal(r.tally.events,1);assert.equal(r.tally.citation,1);assert.equal(r.tally.semantic,0);
assert.equal(r.adversarial.length,7);
assert.equal(r.adversarial.filter(x=>x.classification==='semantic_review').length,6);
assert.equal(r.adversarial.filter(x=>x.classification==='citation_audit').length,1);
const c='- The service does not support all users with daily usage limits.\n';
const d='- The service does support all users with daily usage limits.\n';
r=audit(input(c,d));assert.equal(r.tally.semantic,1);assert.equal(r.matched[0].critical_token_change,true);
r=audit(input(a,a));assert.equal(r.tally.events,0);
r=audit(input(a,'- An entirely unrelated sentence with different contents.\n'));assert.equal(r.tally.unpaired,2);
console.log('PASS: 10 fixture and adversarial invariants');
