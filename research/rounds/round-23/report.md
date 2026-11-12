# Round 23: Bridge-Resolution Failure Injection, Version-Scope Checks, and the Cost of Knowing What to Trust

**Date:** 12 November 2026  
**Continuation:** CDG living record, Rounds 0–22  
**Status:** Controlled synthetic benchmark and deterministic regression tests executed. No independently authored multihop benchmark, trained model, semantic verification, or measured SSD system result.

## Question and decision

Recent rounds repeatedly reproduced a gap between retrieving individually relevant text and assembling an adequate evidence set. A difficult question is whether a more involved graph controller is needed at all. In Round 22, a BM25 control already retrieved 96% of constructed two-paragraph witnesses at a budget of two. Round 23 deliberately tests a different failure mode: *what if the only bridge from a question's subject to the answer is not present in the question, and two apparently valid bridges disagree about version or source scope?*

The immediate verdict is not that we have a new retrieval algorithm. The experiment indicates that inexpensive exact-ID/metadata safeguards can eliminate a class of injected false answers that naïve bridge lookup does not prevent. These safeguards are necessary only when the relevant metadata is complete, trustworthy, and correctly interpreted. Their latency, metadata-index size and correctness against adversarially forged metadata are not measured.

## Experimental design, preregisterable claims, and limitations

The bundled `experiments/round-23/cdg_round23_lab.py` constructs **600 deterministic two-hop examples**, 120 in each of five categories. Each example contains a subject-to-route anchor, a route-to-outcome document when appropriate, and 18 unrelated anchor/route pairs. The question names the subject but deliberately does not reveal its route ID. That is an *engineered lexical disconnection*, not a measurement of naturally authored compositional questions.

The three methods are:

1. **Static BM25 top-2:** retrieves two documents using a minimal independently implemented BM25; may answer only when both the exact subject anchor and its matching route document appear in those two positions.
2. **Naïve bridge lookup:** BM25 retrieves the anchor, extracts its exact route identifier, then selects the first route document with that identifier. It does not check versions, scopes or contradictory anchors.
3. **Guarded lookup:** uses the same BM25 first hop, but consults indexed identity and version metadata, rejects conflicting current anchors, picks the newest version per stable source ID, and requires that the route document match the anchor's source scope. Ambiguity or missing evidence causes abstention.

**Fairness warning:** The guarded policy is allowed to inspect all source metadata without an index/CPU charge; only source text materializations are counted. This is an optimistic proxy, not an equal-cost production comparison. All routes and outcomes are generated using the same easily parsed templates. There is no independent semantic verification and there is no trained relation predictor.

## Results

The following are exact counts from `results.json`, not statistical estimates from real workloads.

| Injected case | Static BM25 @2 correct / 120 | Naïve bridge correct / 120 | Guarded bridge correct / 120 | Why |
|---|---:|---:|---:|---|
| Unambiguous clean bridge | 0 | 120 | 120 | The answer-bearing route has no query subject tokens. |
| Two conflicting current anchors | 120 | 0 | 120 | Both static and guarded abstain; naïve picks an arbitrary route and makes a false claim. |
| Outdated version precedes current version | 0 | 0 | 120 | Guarded lookup uses source identity plus version metadata. |
| Foreign-scope route precedes authorized route | 0 | 0 | 120 | Guarded lookup requires source-scope agreement. |
| Missing second-hop document | 120 | 120 | 120 | All methods abstain; this case does not discriminate methods. |

Here, **correct** includes justified abstentions for the conflicting and missing-evidence cases. Thus these counts are *decision correctness under a fixture-specific policy*, not answer exact-match rates. For the three answerable case types (360 examples), the guarded policy returned the expected synthetic result in all 360. Static retrieval provided no answer under its forced two-document budget. On 240 unanswerable cases, guarded lookup abstained on all 240; this conclusion is specific to the generated metadata and string patterns.

The naïve policy produced **360 invalid answers** across the conflict, version and scope cases. This result is by construction: the contaminating route or older version was inserted ahead of the legitimate one. It is not an empirical error rate for production iterative retrieval.

Mean materialized uncompressed source text bytes per query for the **clean** condition: static 196 B; naïve and guarded 141 B. Under a source-read-only accounting model, the guarded policy is not more expensive than naïve lookup on the clean or version/scope cases, while reading two conflicting anchors (196 B) before abstaining. These figures omit index metadata and query computation, which are exactly where a more elaborate policy may lose its advantage.

**Bug discovered during execution:** An initial implementation checked subject identifiers with substring inclusion. `subject23026` matched `subject2302600`, making every guarded clean case appear ambiguous. Replacing substring matching with exact parsed identifier equality fixed this. The test suite now includes a regression for prefix collisions. This is a genuine implementation lesson: source identity and semantic similarity must not be conflated.

## Graph-of-thoughts branches and cross-links

### Branch A: The bridge can be lexically invisible but structurally accessible

Let a question mention subject `u`. Document `a` states `u -> v`; document `b` states `v -> y`. If `v` and `y` appear nowhere in the question, a lexical one-shot ranker has no query-derived basis to distinguish `b` from unrelated similarly formatted route documents. A second-stage exact-key lookup can retrieve it after inspecting `a`. This is established graph traversal, not new retrieval theory. The relevance of the construction is the *control*: full text need not be retrieved solely because the answer-bearing document has low query similarity.

### Branch B: Identity and authorization are not entailment

An exact route ID does not guarantee that the selected route is the right version, belongs to the same scope, is an independent corroboration, or actually supports a statement. The guard in this fixture handles version and scope **only because trusted metadata is given**. An adversary capable of forging trusted metadata defeats this model. A content hash proves byte identity relative to a known digest; it does not prove authority, authorship, or truth.

### Branch C: Acquiring information versus selecting text

Define a policy state with observed sources `O`, admissible witness hypotheses `W`, source-version constraints `V` and activated physical frames `F`. An acquisition action `a` has incremental cost

\[
C(a\mid F) = C_{\mathrm{CPU}}(a)+C_{\mathrm{metadata}}(a)+C_{\mathrm{reads}}(a\setminus F)+C_{\mathrm{decode}}(a)+C_{\mathrm{tokens}}(a).
\]

A *candidate* decision rule is to acquire evidence only if the expected reduction in decision risk exceeds a cost-weighted penalty. This is standard value-of-information reasoning. It requires **estimated** conditional probabilities, actual cost measurements and shift calibration, none of which is supplied by this round. The union operation over already activated frames is the part that connects to R19's physical layout accounting.

### Branch D: Uncertainty cannot be erased by optimization

When two distinct current anchors have equal authority and conflicting routes, selecting the shorter route, lower frame-read cost or higher BM25 score cannot turn either into verified evidence. The correct policy in the fixture is abstention. If real applications demand an answer, the system needs a distinct authority-resolution process, not merely additional extraction.

### Branch E: Connection to established physical database design

The guard resembles a version-aware join across `(subject, source_id, version, scope, route_id)`, not an exotic neural graph. The likely engineering baseline is a small keyed metadata index plus ordinary seekable source frames. Compare this *first* against a neural witness hypergraph selector. A more complex policy is justified only if it improves held-out QA/citation quality at a matched complete cost.

## Prior-art corrections and new novelty obstacle

- **IndexRAG: Index-Time Reasoning for Multi-Hop Retrieval-Augmented Generation**, Findings of IJCNLP-AACL 2026, https://aclanthology.org/2026.findings-aacl.175/ . Bridge facts materialized at indexing time with single-pass inference are already explicitly studied. Their reported HotpotQA/2WikiMultiHopQA/MuSiQue improvements cannot be compared to this synthetic lab's result.
- **Beyond Static Retrieval: Opportunities and Pitfalls of Iterative Retrieval in GraphRAG**, EMNLP 2026, https://aclanthology.org/2026.emnlp-main.1897/ . Identifies the importance of promoting bridge evidence in iterative retrieval.
- **BridgeRAG: Training-Free Bridge-Conditioned Retrieval**, arXiv April 2026, https://arxiv.org/abs/2604.03384 . Conditions second-hop retrieval on bridge information and reports controlled and benchmark evidence. Further limits novelty of our basic bridge mechanism.
- **HotpotQA**, EMNLP 2018, https://aclanthology.org/D18-1259/ . Independently authored multihop supporting-fact dataset and a necessary next baseline; **not downloaded or evaluated in this round**.

These are *prior-art candidates and baselines*, not reproduced comparisons. Round 23's metadata guards are standard distributed-systems and database concepts. The integration may be worthwhile, but a new-paper claim is not established.

## Reproduction

```bash
python experiments/round-23/cdg_round23_lab.py --output experiments/round-23/results.json
python -m unittest discover -s experiments/round-23 -p 'test_*.py' -v
```

Executed locally using Python 3 and standard library only. Six regression tests passed. Source SHA-256/UTF-8 offset sanity checks passed on a toy Unicode string, but no original-to-canonical map, authenticated citation chain, or live ACL system was implemented. Fixed random seed 23026; no dataset download.

## Next test: a dataset that can falsify the mechanism

**Round 24 P0:** Obtain and checksum the official HotpotQA distractor development split or another authentic multihop benchmark. Freeze question/doc partitions. Measure exact supporting document/sentence recall using common candidate pools. Establish BM25, hybrid, IRCoT-style iterative retrieval, IndexRAG-style bridge materialization, and simple metadata-join baselines. Compare to a frozen answerer on answer and citation correctness.

**Round 24 P1:** Add source-version snapshots, ACL scope, and conflicting source fixtures to an otherwise authentic corpus, with explicit source-authority labels. Test attacks where metadata is missing, corrupted, or fraudulent. Report precision/abstention and the rate of **unsupported answers**, not only selection success.

**Round 24 P2:** Measure real archive/index/metadata bytes, compressed frame union, source reads, decoding CPU and cold/warm p50/p95 on a benchmark host. A controller that merely moves work into metadata scans is not a storage or latency improvement.

**Kill criteria:** If a simple two-hop retrieval baseline plus version/scope join performs as well as the proposed graph controller on matched held-out quality, cost, shift and citation metrics, drop the graph controller. If metadata cannot be authenticated, avoid claiming a safe grounding guarantee. If the only success is on exact-template synthetic data, do not submit a paper arguing a generally better RAG system.
