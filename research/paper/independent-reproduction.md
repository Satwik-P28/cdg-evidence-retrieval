# Independent ACMSE reproduction handoff

This is an executable handoff, NOT evidence of independent human reproduction. Use Linux, a clean checkout at the commit linked in the paper, Python 3.11, a C compiler and system SQLite development headers. Install the same versions used by CI:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install zstandard==0.25.0 gdown==5.2.0 pytest==9.0.2
python experiments/round-136/download_source.py --out external/newsedits
python research/paper/reproduce_acmse.py --source external/newsedits/ap.db --target 10000 --out external/independent-reproduction
```

Use `--rounds 148 151` for a smaller deterministic core check, or `--target 100000` for the full AP cohort once every requested reference is archived. The checker requires the exact source database SHA-256 and compares frozen manifests, physical apparent archive bytes, source payload, reconstruction ratios, counts, observed score error and receipt commitment fingerprints when available. It deliberately does not demand identical timing or process IO. All original subprocess logs are retained, and differences are written to reproduction-report.json. A nonzero exit indicates an execution error, missing reference or mismatch; inspect it rather than editing expected outputs. A new environment may change SQLite page sizes/layout or codec output, which is recorded as a discrepancy. A person independent of the author should provide their name or chosen pseudonym, exact commit, environment, raw report/logs, deviations and outcome. The author should preserve adverse results. No one has yet completed this handoff independently.