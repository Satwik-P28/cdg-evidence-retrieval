#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {temporalWindow,strictMatch}=require('./strict_window.js');
const r={before_object:{label:'Old',time_range:'2025-11-26 to 2025-11-27'},after_object:{label:'New',time_range:'2025-11-27 to ...'}};
assert.equal(temporalWindow('In November 2025, what was true?').start,'2025-11-01');
assert.equal(temporalWindow('In November 2025, what was true?').end,'2025-11-30');
assert.equal(temporalWindow('In 2025, what was true?').end,'2025-12-31');
assert.equal(strictMatch(r,temporalWindow('In November 2025, what was true?')).status,'ambiguous_or_partially_valid');
assert.equal(strictMatch(r,{start:'2025-12-01',end:'2025-12-31'}).label,'New');
assert.equal(strictMatch(r,{start:'2024-01-01',end:'2024-12-31'}).status,'no_applicable_source');
console.log('6 strict-period assertions passed');
