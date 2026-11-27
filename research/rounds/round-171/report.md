# R171: bounded one-hop token tape

Parent R170 207013832a89f294893455b0a0f3b50421429f1d. R170 corrected AP 10,009 and CLARK passed (45917370202), largest AP pending at inspection. AP bytes: positional 20684800, adaptive 18583552, frequency 14082048, text joint 24633344, integer 23986176, integer joint 23986176. AP integer joint rejected all 8373 nonempty non-parent source candidates by decoded-byte bound. Text joint selected 2171 but increased total size. R167 large AP adaptive 132960256, R168 weighted 132964352, R169 independent 132964352. R169 strengthened CI 45917035075 all passed; 8109 large AP candidates, zero accepted.

## Design
Use same article's last four previously full token tapes as raw Zstd dictionary candidates; preserve one-hop dependency. Compare against independently compressed payload, require 20% payload reduction, parent+child decoded bytes <=2.5x child and activated payload <=1.5x independent tape payload. Charge both frames on phrase candidate reads and source recovery. For text joint, source bound counts raw output plus materialized child and parent tape. Never replace an existing source parent. All pages charged; source/index selection remains greedy. Include same-schema full text and integer baselines, positional, adaptive and frequency; drop integer joint from corpus matrix since R170 already rejected all candidates, and adding a parent only tightens bound. Verify every stored tape after reopen, all source bytes, exact BM25+DF, and tape logical bounds. No physical IO claim.

## Local synthetic probe (actually executed)
System libzstd level 3 via ctypes, SQLite 3.46.1; 100 articles, 10 versions each, 500 tokens from 20,000 possible IDs, 4 edit regimes; 16,000 exact tape recovery/bound checks across 16 databases. Physical sizes, tape table only (no vocabulary/postings/source frames). Full and delta identical schema. Metadata cost proxy 8 bytes; same one-hop ratio gates. 
| Tokens replaced/version | Text full | Text delta | ID full | ID delta | Text/ID admitted |
|---:|---:|---:|---:|---:|---:|
|1|2056192|282624|1376256|212992|900/900|
|20|2056192|679936|1376256|471040|882/900|
|150|2056192|1376256|1376256|1032192|495/500|
|500|2056192|2056192|1376256|1376256|0/0|

Synthetic only. Strong gains on small edits, no degradation in fully changed regime in this fixture. Corpus and source joint performance unverified. R171 should not assert novelty over dictionary compression; its question is whether reduced tape duplication makes the joint representation viable.
