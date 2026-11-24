# R134: native Git pack as a strong external source storage control

Status: all four original-code jobs passed.

Actual git pack-objects with compression 9, window 10, depth 1/8/50, single thread and path hints. Inputs are unique source blobs from the four largest previously fixed cohorts. Git may select across documents and future revisions; deliberately give offline storage an advantage. Charge .pack, .idx and auxiliary pack files plus an actual SQLite positional index, provenance, receipt ledger and per-revision object pointer. Do not charge scratch loose objects or empty Git repository scaffolding. Build independent snapshot and frozen CDG controls and enforce equality to prior archive byte totals and workload hashes. Reconstruct every revision through persistent git cat-file and check Git SHA1, SHA256 and byte equality. Verify every historical rank against rebuilt active native index, and require identical receipt bodies and replays under every representation.

This is feature-matched for finalized historical readback, NOT for transactional append, pinned-reader updates or crash recovery. Never imply Git pack offers equivalent update semantics. Logical pack-entry activated bytes include headers; decoded work sums reconstructed blob sizes and does not measure delta instructions, page traffic or caching. Persistent subprocess timing is descriptive only. Compare read-only storage and depth honestly; if Git wins, report it. No direct TimIR or WikECD implementation comparison yet. Documentation: https://git-scm.com/docs/git-pack-objects and https://git-scm.com/docs/git-verify-pack .

## Results

All four original-code jobs passed on 6635c9d163c1dea640ccf1ccd4f5593032af2512 (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45498911419), with 8,975 exact source readbacks, 6,400 historical rank checks and zero observed BM25 score error. Native Git packfiles at depth 1 produce smaller finalized archives than CDG in every corpus: CDG incurs a 6.4–11.5% complete-archive premium. Worst-request logical decoded ratios for CDG are 2.04–2.25x versus 3.04–12.66x for depth-1 Git. Mean logical decoded work is also lower for CDG, but the difference is modest. Git pack depth does not constrain relative reconstructed byte volume: a single large parent can exceed a small requested object by an arbitrary factor. These are empirical finalized readback comparisons, not matched incremental updates or crash semantics. Git uses offline cross-document selection and charges entry headers in activation accounting. Its compressed objects reside outside SQLite, unlike CDG, so page-layout effects contribute to total size differences. This motivates an additional layout-matched control; no pure codec or timing superiority claim.

| Corpus | Policy | Total archive B | Mean decode ratio | Max decode ratio | Max activated ratio | Depth |
|---|---|---:|---:|---:|---:|---:|
| k8sdocs | snapshot | 3334144 | 1.0000 | 1.0000 | 1.0000 | 0 |
| k8sdocs | bounded_anchor | 2215936 | 1.7797 | 2.2496 | 1.4090 | 1 |
| k8sdocs | git_pack_depth1 | 1987197 | 1.9217 | 11.2576 | 8.4506 | 1 |
| k8sdocs | git_pack_depth8 | 1937308 | 2.8807 | 30.5929 | 10.9250 | 5 |
| k8sdocs | git_pack_depth50 | 1936778 | 3.5098 | 30.5929 | 10.9250 | 7 |
| bips | snapshot | 7589888 | 1.0000 | 1.0000 | 1.0000 | 0 |
| bips | bounded_anchor | 4780032 | 1.8559 | 2.0696 | 1.2077 | 1 |
| bips | git_pack_depth1 | 4481814 | 1.9100 | 3.0444 | 2.5605 | 1 |
| bips | git_pack_depth8 | 4423074 | 3.0208 | 8.3150 | 2.7034 | 7 |
| bips | git_pack_depth50 | 4422008 | 3.5723 | 10.4394 | 2.7168 | 9 |
| cpython | snapshot | 9166848 | 1.0000 | 1.0000 | 1.0000 | 0 |
| cpython | bounded_anchor | 5210112 | 1.8557 | 2.0360 | 1.1583 | 1 |
| cpython | git_pack_depth1 | 4896182 | 1.9061 | 12.6649 | 9.0721 | 1 |
| cpython | git_pack_depth8 | 4807716 | 3.1593 | 8.2150 | 1.6265 | 7 |
| cpython | git_pack_depth50 | 4806305 | 3.8686 | 12.3863 | 1.6265 | 11 |
| gitdocs | snapshot | 9461760 | 1.0000 | 1.0000 | 1.0000 | 0 |
| gitdocs | bounded_anchor | 5582848 | 1.8203 | 2.1584 | 1.2603 | 1 |
| gitdocs | git_pack_depth1 | 5008193 | 1.8711 | 3.0358 | 1.9381 | 1 |
| gitdocs | git_pack_depth8 | 4932777 | 2.8900 | 8.1857 | 1.9752 | 7 |
| gitdocs | git_pack_depth50 | 4930576 | 3.2654 | 11.4523 | 1.9785 | 10 |
