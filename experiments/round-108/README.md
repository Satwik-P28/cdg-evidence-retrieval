# CDG R108: genuine-source logical posting codecs

Run from repository root, with `experiments/round-107/barm.py` and existing immutable-data readers in `experiments/round-83` and `experiments/round-96`:

```bash
python -m pip install pytest==9.0.2
python -m pytest -q experiments/round-108
python experiments/round-108/authentic_postings.py --dataset qasper --out experiments/round-108/ci-qasper.json
python experiments/round-108/authentic_postings.py --dataset scifact --out experiments/round-108/ci-scifact.json
```

QASPER v0.3 and SciFact data are fetched only from the official pinned upstream archives, and SHA and schema deviations fail closed. Results save aggregate counts, no source/queries.

The StreamVByte control is a scalar reference with the format's 2-bit widths, not SIMD. Variable-partition Elias-Fano uses a length-optimal *in-sample* DP over restricted candidate partition lengths, not a production PEF library. All bytes account for length headers and independent block reconstruction. No actual native SQLite index coding or RAG retrieval behavior is changed.

## Decision gate

If BARM does not outperform strong ordinary controls on original postings, it remains a negative control; do not build CDG around the RH name. For publication a useful next step would replace SQLite index segments or integrate an external exact search index with random-access APIs and fair total storage and latency.