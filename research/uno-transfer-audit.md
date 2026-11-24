# Uno transfer audit and publication scope (2026-11-24)

## Sources inspected
- Sahoo et al., [Unlocking Lossless Speedups in LLMs via Discrete Diffusion](https://arxiv.org/abs/2609.04010), September 2026 preprint.
- Authors' [November 9 Kempner Institute technical exposition](https://kempnerinstitute.harvard.edu/research/deeper-learning/unlocking-lossless-speedups-in-llms-via-discrete-diffusion/): frozen AR parameters, gated conditional LoRA diffusion pathway, one-step distillation, TV objective, rejection/correction and linear/tree verification.
- [Uno source](https://github.com/ifm-ai/uno/tree/fdfa90da33e5882706c5eca8068fd5ab03dcf543) inspected README and sampler; CUDA/FlashAttention runtime, 0.9B/7B/8B model recipes. No checkpoint executed.
- [Leviathan et al. speculative decoding](https://arxiv.org/abs/2211.17192); [Ding and Suel, block-max indexes](https://doi.org/10.1145/2009916.2010048); [Yan et al., invocation bottleneck in LLM compression](https://arxiv.org/abs/2611.05871). Recent speculative entropy decoding work also exists; do not claim novelty without full literature review.

## Three distinct exactness contracts
Uno preserves the base model's sampling distribution, not an identical
random sample, truthfulness, or a compressed byte stream. CDG source
storage requires bit-exact reconstruction and trusted source digests.
CDG historical retrieval requires exact snapshot-specific DF/lengths,
ranked IDs, scores and tie order under its declared contract. A proposal
may change work order but cannot determine the answer. An entropy decoder
must obey the actual bitstream and exact integer CDF at every accepted
prefix; accepting an independently sampled plausible token is incorrect.

## Transfer priorities
1. R128 verified candidate ordering: prior results seed top-k, safe
   current-snapshot bounds certify skipped candidates. Established dynamic
   pruning; explicitly charge bound/draft overhead and compare no draft.
2. Future exact compressed block scheduling: persist conservative bounds
   and separate exact historical DF; use a proposal only for activation
   order. Need physical metadata bytes, actual skipped decoded bytes,
   native FTS5 and stronger pruning baseline, independent histories.
3. Atlas generator experiment, separate from paper: released Uno 0.9B
   first, then a supported GPU 8B model; fixed identical model, evidence,
   prompt and generation settings; TTFT, TPOT, throughput, memory, output
   distribution checks, answer/citation accuracy. No H200 numbers
   extrapolated to local hardware. Greedy sequence checks are not a
   proof of sampling equality. Runtime and training cost must be charged.
4. Neural entropy decoding experiment, separate future paper: speculative
   branches verified by the authoritative entropy decoder and integer
   CDFs, transactional rollback on mismatch; compare bitstream identity,
   rate, bytes, memory, target forward calls, CPU/GPU wall time. Compare
   against existing speculative entropy decoding and block-parallel
   coding. No neural compression or model training needed for current CDG.

## Paper scope lock
Working title: Storage-Efficient Reproducible Evidence Retrieval in Evolving
Document Collections. Keep a narrow systems contribution: exact versioned
source reconstruction, snapshot-specific ranking, replayable evidence
receipts, and measured archive/index tradeoffs. Uno is adjacent motivation
or future work, not a proven component or an original contribution.
R115/116/119/120 source and atomic evidence work is stronger than a new
unvalidated learned predictor. R121–127 positional/TF controls show why
native positional FTS5 remains default. Validate on independent genuine
revision histories and charge all source/index/mapping/WAL bytes before
claiming end-to-end storage or speed improvement. No hallucination
reduction claim. No further tuning on Versions as primary evaluation.


## R128 outcome

Rank-stage experiment passed exact comparisons (636 per method). On the final cutoff, dynamic block bounds skip 68.79% of candidate scoring, but bound construction makes median rank-stage latency 1.94x slower than exhaustive sorting. Prior-cutoff proposals further worsen median/p95. No compressed data activation was avoided or measured. Defer speculative scheduling until an inexpensive persisted bound scheme is evaluated on independent data. [Report](rounds/round-128/report.md).
