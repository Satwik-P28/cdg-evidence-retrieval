# Round 59: Frozen Global Evidence Budget Confirmation on the Last 256 Development Questions

**Date:** 2026-11-17. **Status:** successful GitHub Actions run 44165816726, three dedicated unit tests passed. Questions were the final 256 ID-locked examples of the Round 54 512-question sample, **not** used in the Round 57 sentence allocation experiment. The source question family and previously reported Round 54 full-sample document results are shared, so this is a separate allocation test partition, not an independent new corpus.

## Prespecified primary hypothesis

Round 57's first two partitions suggested rank-frontloaded allocation (4/3/1/1/1) might improve complete gold support recovery and reduce compressed-frame activation compared with uniform two-per-document selection. The critical comparator for equal **at-most-ten** sentence budgets is **uniform two with unused slots recycled**, because uniform two frequently leaves 0.4-0.5 budget positions unfilled. The primary comparison was frozen as frontloaded versus recycled uniform before sentence allocation was measured for these remaining questions.

Hold all else fixed: original R25 title-bridge retrieval (up to five documents), global FTS5 BM25 sentence rank, a fixed maximum of 10 sentences, original exact SHA source receipts, and ideal within-query deduplication of compressed frame activations. Do not inspect gold annotations for allocation. Secondary controls: naive uniform two, balanced 3/3/2/1/1, reversed ranking, and deterministic random selection.

Sample question ID SHA-256: **1d844fa402f0a8a516beef626813e2153c95f4ded6f26c35e35e667cb6dd5d4c**. Of the 256 questions, 199 are bridge and 57 comparison. Full selected-document gold-set availability is **223/256**, the maximum achievable complete annotated support recall without additional document retrieval.

## Results

| Fixed-budget allocation | Complete gold support sets /256 | Mean gear512 compressed bytes per question | Mean selected sentence count |
| --- | ---: | ---: | ---: |
| Naive uniform 2 each | 175 | 1,569.984 | 9.590 |
| Uniform plus recycling | **183** | 1,573.371 | 9.980 |
| Front 4/3/1/1/1 | 187 | **1,533.211** | 9.980 |
| Balanced 3/3/2/1/1 | **191** | 1,543.539 | 9.980 |
| Reverse 1/1/2/3/3 | 142 | 1,575.777 | 9.980 |
| Deterministic random | 63 | 1,498.809 | 9.980 |

The whole-source Zlib mean compressed activation for all nonrandom allocations is **1,598.871 bytes**, because the sampled snippets touch the same set of whole source frames. Source index bytes and archive bytes are recorded in the raw results, along with complete UTF-8 receipt verification.

## Primary statistical check

Front 4/3/1/1/1 versus recycled uniform:
- Both recover full gold sentence sets on 167 questions;
- Front succeeds alone on 20; recycled uniform succeeds alone on 16;
- Neither succeeds on 53;
- Net difference **+4/256 = +1.5625 percentage points**;
- Two-sided exact discordance test **p = 0.617719317**;
- 4,000-resample seeded paired percentile 95% interval **[-3.125, +6.25] percentage points**.

This does **not** provide persuasive evidence that frontloading generalizes. The observed compressed byte reduction (~2.55% versus recycled uniform) is a narrow measurement under idealized frame reuse, not a production I/O or end-to-end token advantage.

Balanced allocation obtained +8 additional recoveries versus recycled uniform, with an exploratory exact two-sided discordance p = 0.16864 and paired 95% bootstrap interval [-0.781, +7.031] percentage points. This secondary comparison also lacks convincing evidence.

Uniform recycling versus naive uniform recovered **8** additional complete gold support sets with no losses, an inevitable monotonic behavior for selecting a superset of evidence when otherwise unused global budget positions are filled. It consumes more actual sentences and marginally more read traffic. This is conventional budget-accounting correctness, not a new retrieval algorithm.

## Decision after falsification

**Do not promote rank-frontloaded or balanced allocation as a generally better evidence selector.** Directional gains from two exploratory groups substantially weakened on the frozen remaining tranche under the correct recycled-uniform comparator. Keep both as research variants and negative-evidence context.

**Keep safe mechanical default:** utilize the full allowable global sentence budget by recycling unused slots, because adding additional evidence cannot reduce annotation coverage when all previous selected sentences remain. Real systems must still charge source, model-token, cache and latency costs.

The highest-priority next evaluation is more independent corpus families, model-level claim support, and fully charged retrieval/index/token cost. No new hallucination guarantee or compressive superiority has been established by this round.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-59 -p 'test_*.py' -v
    python experiments/round-59/confirm_budget.py --out experiments/round-59/results.json

CI: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44165816726 . The HotpotQA development corpus is downloaded transiently, checked against fixed SHA-256 and not redistributed.
