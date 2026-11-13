# Repository integrity and research provenance (Round 25)

The root `MANIFEST.json` was generated for an earlier archive state, before the latest research additions. It should not be described as a current file-by-file audit. Use the current committed Git tree and `git ls-files` for membership, or regenerate full SHA-256 checksums after cloning:

```bash
git ls-files -z | xargs -0 sha256sum > checked-files.sha256
```

Do not add `checked-files.sha256` to the same manifest without defining a self-reference exclusion. Historical result JSON files indicate which analyses were run against connected sources, which were synthetic, and which were actually rerun locally. Round 25's full-context raw source remains in the upstream pinned repository, not the CDG repository.

The Round 25 Python test suite checks parser and selection invariants; it does not certify reproducibility of the 100-example numerical experiment. That requires downloading SHA-verified upstream data and running the full evaluator.
