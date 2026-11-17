#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {asof,interval,matching,parseCsv,evaluate}=require('./temporal.js');
assert.equal(asof('Since February 2025, who held office?').date,'2025-02-28');
assert.equal(asof('In 2018, who held office?').date,'2018-07-01');
assert.equal(asof('Between 2010 and 2012, who held office?').date,'2011-07-01');
assert.equal(interval('2010-01-01 to ...').end,'9999-12-31');
const r={before_object:{label:'Old',time_range:'2020-01-01 to 2022-01-01'},after_object:{label:'New',time_range:'2024-01-01 to ...'}};
assert.equal(matching(r,'2021-01-01').length,1);
assert.equal(matching(r,'2023-01-01').length,0);
assert.equal(matching(r,'2025-01-01')[0].label,'New');
const ambiguous={before_object:{label:'Old',time_range:'2020-01-01 to ...'},after_object:{label:'New',time_range:'2024-01-01 to ...'}};
assert.equal(matching(ambiguous,'2025-01-01').length,2);
assert.equal(parseCsv('1,"[{""type"":""before"",""question"":[""In 2020?""],""answer"":""Old""}]"').length,1);
console.log('9 temporal fixture assertions passed');
