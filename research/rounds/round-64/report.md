# Round 64: Retroactive Lossless Re-Encoding on Real Source Histories

**Date:** 2026-11-17. **Status:** full upstream-data run and six dedicated regression tests passed in GitHub Actions run **44184798456**. This is an engineering exploratory architecture experiment, not a new codec or proof of optimal online compression.

## Hypothesis

A future-blind source archiver cannot know whether a first source version will have enough descendants to benefit from content-defined framing. R63's similarity threshold suppresses valuable framing on early related sources. Would **retroactive promotion** help?

When a source arrives, measure fraction of current 96-byte overlapping shingle fingerprints contained in the most similar **prior** source. If at least 0.20, archive the arriving source as gear512-Zlib frames; if its closest previous source remains whole-Zlib, migrate that prior source to gear frames too. Keep the original source ID and SHA-256 intact. The archived source bytes must still reproduce exactly after migration. Content-addressed frame references are updated and unreferenced compressed payloads are garbage-collected.

The selected threshold 0.20 is inherited from R63, not refit here. Compared five conventional streaming controls: always whole, always gear, known source-family label (oracle), threshold gate without migration, and threshold with migration. Also compare the original R58 ungated online read-weighted archive as a separate control.

## Input families

Previously examined R62/63 histories: Ruff 12 revisions, Transformers 12, Flask 7. **Additional first-pass transfer histories:** vLLM 12 genuine README file revisions under pinned cutoff 935f87de846980dc16c54ac1996595fc12eb3f9e (Apache-2.0), and Pydantic 12 under pinned cutoff e56f60fd32273d1d7c397a3ac46bba05e6a73454 (MIT). All sources are fetched from immutable upstream Git commits, independently hashed, not redistributed. Each history is combined with 0, 128 and 512 fixed source paragraphs.

## Key results for 512 unrelated paragraphs

| History | Whole Zlib archive bytes | R58 ungated archive bytes | Retroactive migration bytes | Migration benefit vs ungated | Prior sources migrated |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ruff | 262,918 | 209,393 | **205,672** | -1.78% | 3 |
| Transformers | 261,985 | 205,427 | **201,702** | -1.81% | 4 |
| Flask | **188,846** | 192,454 | 189,217 | -1.68%, but **0.20% larger than whole** | 3 |
| vLLM (new family) | 232,706 | **213,624** | 214,680 | **+0.49% worse than ungated** | 4 |
| Pydantic (new family) | 200,301 | 195,868 | **192,136** | -1.91% | 3 |

The migration policy helps archive size relative to the R58 ungated online reference for four of five families under this mixture, but the previously unused vLLM history is an explicit **counterexample**. Flask remains worse than plain whole-Zlib despite the migration improvement relative to ungated.

At zero independent paragraphs, migration matches the ungated archive size for Ruff (22,671 bytes), Transformers (18,699 bytes), and Pydantic (9,166 bytes). It is larger than ungated for Flask and vLLM, demonstrating that recoding is not automatically useful even before unrelated sources are mixed.

## Charged mutation costs and honest boundary

For 512 independent paragraphs:
- Ruff: 3 prior sources rewritten; source plaintext reread 39,993 B; compressed old-source read bytes 13,695 B.
- Transformers: 4 prior sources rewritten; plaintext reread 52,819 B; compressed reread 20,083 B.
- Flask: 3 prior sources rewritten; plaintext reread 3,649 B; compressed reread 2,047 B.
- vLLM: 4 prior sources rewritten; plaintext reread 33,979 B; compressed reread 13,897 B.
- Pydantic: 3 prior sources rewritten; plaintext reread 7,196 B; compressed reread 3,202 B.

**Prototype metadata write problem:** A compressed binary manifest is rewritten in full after every arrival. The sum of serialized manifest writes under 500-plus appended sources is approximately **5.1–5.8 MB**, even though the final archive is only 189–215 KB. Most of this amplification affects *all* streaming policies under this naive full-rewrite format, not solely the extra source migrations. It must not be misrepresented as an inherent cost of migration. A real WAL/LSM, append-only log, or copy-on-write metadata implementation would be a fairer control. This drives Round 65.

Other costs: source fingerprints reside in Python RAM and are not included in archive bytes; the prototype does not implement atomic manifest publication, fsync crash durability or true physical I/O. The compressed bytes for partial source spans are counted under exact SHA source readback but are not measured SSD traffic.

## Research decision

**Do not promote** retroactive re-encoding as the default. It offers small, real storage improvements in multiple source families, but not uniformly, and it adds rewrite and publication complexity. The initial storage advantage is too small to outweigh unknown reliability, memory, update throughput and physical I/O costs without further controls.

Keep the implementation as a research candidate. The next falsifier is a fair compact metadata update baseline with replay, checkpoint cost and corruption detection, followed by independently timestamped source families beyond current upstream README histories and a full evidence index/verification workload.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-64 -p 'test_*.py' -v
    python experiments/round-64/retroactive_promotion.py --out experiments/round-64/results.json

CI: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44184798456 . Mature CAS, content-defined chunking, replay logs, and migration policies are established systems concepts; this work does not demonstrate a new theoretical compression bound or a full RAG model advantage.
