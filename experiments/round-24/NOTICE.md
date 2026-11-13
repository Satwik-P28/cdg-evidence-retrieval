# Dataset provenance for the Round 24 question-only diagnostic

No HotpotQA question or document datasets are bundled here. The files retrieved by `fetch_upstream.py` originate from `surpradhan/rag-benchmark` at commit `c9dc6c350accb3c07629f0465e57d38756a006b0`, which describes its questions as derived from HotpotQA. See the [official HotpotQA project](https://github.com/hotpotqa/hotpot) for corpus provenance and the CC BY-SA 4.0 dataset license.

The benchmark is a closed-world, label-derived title-list diagnostic. Source content and original sentence annotations were **not** evaluated. The upstream file's `test` designation is not an official blinded test split. Only score aggregates and local reproducibility code are committed, not the redistributed question files.
