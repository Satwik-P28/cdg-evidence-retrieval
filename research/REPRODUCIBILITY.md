# Reproducibility

Everything below was executed in an unprivileged Linux container (2 vCPU, 3 GB RAM,
7.8 GB disk, no root). Commands are given exactly as run.

## Branches and commits

| Item | Value |
|---|---|
| Repository | `Satwik-P28/cdg-evidence-retrieval` |
| Start branch | `research/round-165-r172-selective-positions` |
| Start commit | `7731bebe` |
| Working branch | `research/round-173-r178-block-postings` |
| R173 (block postings) | `6537be4` |
| R174 (cost-based selection) | `a4d7953` |
| R175 (joint layout) | `fce2b81` |
| R176 (external codecs) | `d14ba43` |
| R177 (adversarial) | `3d61254` |
| Merge to `main` | **not performed** (research branch only) |

## Corpus identities

| Corpus | Identity | How obtained |
|---|---|---|
| AP NewsEdits, 10,009 revisions | manifest `2788f97b57da9dabb24ace843b8f4b9b0993fc1041c9dfcca228ab6e26a79857` | `python experiments/round-136/download_source.py --out external/newsedits` |
| CLARK, 1,161 revisions | manifest `1567b6c765b7a648e1a2a6d4221bf22543a7011377fda94161c37c04a29b6e2f` | `zip` from ERASE at commit `b93f898780b3cf40fedd4e9a00c51af9a27688bc` |
| Frozen query plan | `query_plan_sha256` `c6f41c9c9b4bc59df09cbf92f79e90ea05e76ea5b19426584172d58dbcc91e2d` | derived from the native oracle at the first cutoff, no randomness |

Every runner re-derives the manifest and raises if it differs, so a drifted dataset
cannot silently produce numbers.

## Determinism

* Query plans: deterministic given the corpus and the first cutoff.
* Arm order: `--only` and merge-on-rerun; no dependence on filesystem order.
* Query shuffles: `random.Random(173)` (R173), `175` (R175), `177` (R177), `1000+rep`
  (R177 repetitions) — recorded in the code.
* Selection splits (R174): salted hash of the query text, salt `r174`, first byte
  mod 10 (`<6` train, `6–7` validation, `8–9` held-out). Split manifests are in
  `experiments/round-174/results-*.json` under `split_manifest`.
* Codec and block choices: enumerated, not sampled.

## Environment

```
python 3.11 / 3.12 (venv at /tmp/venv)
zstandard==0.25.0  pytest==9.0.2  pyflakes==3.4.0  rapidfuzz==3.14.3  gdown==5.2.0
gcc (built the SQLite extension and the native block kernel)
```

Two build steps need care in a bare container:

1. **No `libsqlite3-dev`, no root.** The FTS5 extension is compiled against the
   SQLite 3.46.1 amalgamation headers unpacked to `/tmp/sqlincl`:
   `cc -O3 -shared -fPIC experiments/round-152/cdgfts.c -I/tmp/sqlincl -o experiments/round-152/cdgfts.so`
2. **Native block kernel** (optional, 1.6× faster phrase path):
   `cc -O3 -shared -fPIC experiments/round-173/cdgbp.c -o experiments/round-173/cdgbp.so`
   The Python decoders remain the reference and the tests run without the kernel
   (one test skips).

## Commands per round

```bash
# tests
CDG_FTS_EXTENSION="$PWD/experiments/round-152/cdgfts.so" \
PYTHONPATH=experiments/round-173:experiments/round-174:experiments/round-175 \
/tmp/venv/bin/python -m pytest -q experiments/round-173 experiments/round-174 experiments/round-175

# R173 block-addressable positions (probe + measurement)
CDG_FTS_EXTENSION="$PWD/experiments/round-152/cdgfts.so" CDG_BLOCK_KERNEL="$PWD/experiments/round-173/cdgbp.so" \
PYTHONPATH=experiments/round-173 /tmp/venv/bin/python research/rounds/round-173/probe.py
PYTHONPATH=experiments/round-173 /tmp/venv/bin/python experiments/round-173/blocked_positions.py \
  --source external/newsedits/ap.db --target 10000 --extension experiments/round-152/cdgfts.so \
  --out experiments/round-173/results-ap-10009.json

# R174 cost-based selection (41 arms over budgets 1/2/5/10/20/40%)
PYTHONPATH=experiments/round-173:experiments/round-174 /tmp/venv/bin/python experiments/round-174/cost_selection.py \
  --source external/newsedits/ap.db --corpus ap --target 10000 \
  --extension experiments/round-152/cdgfts.so --out experiments/round-174/results-ap-10009.json

# the same run can be split over several invocations: --only takes a comma list and
# an existing output file with a matching manifest is updated in place, so
#   --only "df-1%-greedy,train_candidates-2%-greedy"
# followed by a second invocation covering the remaining arms reproduces the same set.

# R175 joint layout
PYTHONPATH=experiments/round-173:experiments/round-174:experiments/round-175 /tmp/venv/bin/python \
  experiments/round-175/joint_layout.py --source external/newsedits/ap.db --target 10000 \
  --extension experiments/round-152/cdgfts.so --out experiments/round-175/results-ap-10009.json

# R176 external codecs
PYTHONPATH=experiments/round-173:experiments/round-176 /tmp/venv/bin/python experiments/round-176/external_codecs.py \
  --corpus ap --source external/newsedits/ap.db --target 10000 \
  --extension experiments/round-152/cdgfts.so --out experiments/round-176/results-ap-10009.json

# R177 adversarial (synthetic + both corpora)
PYTHONPATH=experiments/round-173 /tmp/venv/bin/python experiments/round-177/adversarial.py \
  --corpus synthetic --extension experiments/round-152/cdgfts.so --out experiments/round-177/results-synthetic.json
PYTHONPATH=experiments/round-173 /tmp/venv/bin/python experiments/round-177/adversarial.py \
  --corpus ap --source external/newsedits/ap.db --reps 5 \
  --extension experiments/round-152/cdgfts.so --out experiments/round-177/results-ap-10009.json
```

## Hosted CI

| Workflow | Matrix | Purpose |
|---|---|---|
| `.github/workflows/cdg-r173-blocked.yml` | AP 10k, AP 100k, CLARK | reproduce R173 numbers on a clean runner |
| `.github/workflows/cdg-r174-selection.yml` | AP 10k, CLARK | reproduce R174 |
| `.github/workflows/cdg-r175-joint.yml` | AP 10k, AP 100k, CLARK | reproduce R175 |
| `.github/workflows/cdg-r176-external.yml` | AP 10k, CLARK | reproduce R176 |
| `.github/workflows/cdg-r177-adversarial.yml` | synthetic, AP 10k, CLARK | reproduce R177 |

All workflows compile both C files with `-Wall -Wextra -Werror`, run `pyflakes`, run
the round's tests, then run the measurement and upload the JSON artifact.

## What is not reproducible here

* **AP 100,000 in CI only.** Run 45919907942 started it; the artifact download
  returns 401 from this environment (no GitHub token). The 74,364-revision figures
  quoted anywhere as CI-reported are not used as evidence.
* **Cold cache.** Cannot drop the page cache without root.
* **Physical I/O.** No `strace`/`perf` instrumentation available; "activated bytes"
  are logical counts maintained by the readers.
* **External systems.** PISA, FastPFor, CRoaring and folly were cloned and read, not
  built. Their numbers in R176 are size computations of the published layouts on our
  data, implemented in `experiments/round-176/external_codecs.py` and pinned by
  16 known-answer tests.
* **Between-run variance.** A single machine with a noisy neighbour produced up to
  25% p95 swings between processes; R177 quantifies within-run variance (CV 1.3–4.8%)
  but cannot control between-run effects.

## Artefact inventory

```
experiments/round-173/{blocked_positions.py, cdgbp.c, tests/, results-ap-10009.json, results-clark-1161.json}
experiments/round-174/{cost_selection.py, tests/, results-ap-10009.json, results-clark-1161.json,
                        results-ap-10009-run1.json, results-clark-1161-run1.json}
experiments/round-175/{joint_layout.py, tests/, results-ap-10009.json}
experiments/round-176/{external_codecs.py, tests/, results-ap-10009.json}
experiments/round-177/{adversarial.py, results-synthetic.json, results-ap-10009.json, results-clark-1161.json}
research/rounds/round-173/{audit.md, report.md, probe.py}
research/rounds/round-174/report.md
research/rounds/round-175/report.md
research/rounds/round-176/{report.md, external.md}
research/rounds/round-177/report.md
```

Test counts actually executed: R173 27 passed (26 + 1 skip without the native kernel),
R174 8 passed, R175 13 passed, R176 16 passed, R177 7 synthetic suites × all cutoffs
(261 rank checks) + 2 corruption probes + 9 coefficient cases.
