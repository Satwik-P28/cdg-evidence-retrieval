# R189 local lexical-key representation probe

Actual local execution, Python 3.13.5, SQLite 3.46.1, zlib. Source vocabulary sampled from installed Python standard library top-level Python source files (manifest ed5db8e23347aaf7c607fa1db274958c2bb2db2f8fcb0a68d81f327d7b5d9b2b); synthetic edits to 31-token snippets, regex tokenizer not Unicode61. Two seeds 189/190, 400/1600 pairs, substitution/mixed edits, 64 phrases per workload. Eight cases x six arms, 6,144,000 pair-query correction comparisons, all passed. Compare direct UTF-8 token keys vs fixed16 lexicographic IDs with fully persisted lexicon, three compressed block targets 450/900/1800 B. All patch database pages charged. Integer queries perform SQLite lookup per token; no resident mapping in measured path. No full archive, real edit history, BM25, or source reconstruction claim. Timing single local run, noisy (one UTF8 case substantial variation).

| Target | Median ID / UTF8 bytes | Median ID / UTF8 P95 | ID smaller | ID faster |
|---|---:|---:|---:|---:|
|450|0.7031|1.3363|8/8|1/8|
|900|0.7224|1.3480|8/8|1/8|
|1800|0.7532|1.2780|8/8|1/8|

At 900 B target ID lexicon pages 32768–69632 bytes, vocabulary 1759–4286. Total ID size range 66.3%–79.5% of UTF8. The 1800 B target approximately doubles size relative to 900 B (median 2.10x IDs / 2.05x UTF8), because large WITHOUT ROWID records spill across pages. 450 B is about 9–10% larger than 900 B. Key compression and page-aware layout interact. IDs might be promising if dictionary lookups can be batched or resident mapping with explicitly charged RSS; not a proven latency improvement. All raw results, exact executed local source, dependency probe and logs separately supplied as CDG-R189-lexical-encoding.zip. No direct RH theorem application. This report only, not code, in repository.
