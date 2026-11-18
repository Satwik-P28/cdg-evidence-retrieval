# CDG Research Continuation: Rounds 74–78

**Updated:** 18 November 2026. This addendum extends the main repository's \`research/living-record-rounds-33-73.md\`. R74–77 full reports are maintained in the pending documentation review at PR #20; this addendum is separate to prevent silently claiming their merge. Follow their actual repository status before citing paths on main.

| Round | Experiment | Observed evidence and decision |
| --- | --- | --- |
| 74 | Frozen QA-train NLI calibration transferred to independent Data2txt test source groups | Cross-task FPR and source serialization moved substantially; 0.50 threshold rejected all 96 Data2txt responses. Reject naïve threshold transfer. |
| 75 | Same answer, actual versus nearest alternate source, generic NLI | Worst-claim entailment actual-minus-swap mean +0.00023; source-group interval spans 0. Other aggregations move more. Reject worst-claim sensitivity as reliable evidence-dependence test. Swaps are not independent counterfactual truth labels. |
| 76 | Published RAGTruth-trained LettuceDetect on R72 fixed human QA+Summary test cohort | 141 responses: TP14/FP16/FN17/TN94, response F1 0.459, character F1 0.405. Strong in-domain pretrained baseline, not independent transfer. |
| 77 | Original generator prompt versus reconstructed source context, identical detector/answers | 5/141 response decisions differ; response F1 0.459 to 0.484; source-group bootstrap interval includes 0. No reliable superiority. PR #19 contains code; PR #20 contains documentation. |
| 78 | Source CAS receipt -> exact original byte prefix -> task context -> pretrained LettuceDetect -> human evaluation | **Measured and passed:** 141/141 original-vs-archive model masks equal, 48 full reads and 282 response receipts verified; whole archive 28,398 B versus gear 35,437 B; original and archived F1 0.45902. Existing detector, no accuracy gain claimed. |

## Graph-of-thoughts update

**Reliable provenance** (R48 and R73) -> **identity-preserving archive-fed model input** (R78). This edge can be proven by byte comparisons, but it does **not** prove semantic entailment.

**Response-conditioned semantics** (R72 and R74) -> **sensitivity to counterfactual sources** (R75). Worst-claim aggregation behaves almost invariantly under tested swaps; a representation/aggregation improvement must beat this fixed negative control, not merely return different-looking confidence scores.

**Task-specific trained semantics** (R76) -> **prompt construction robustness** (R77) -> **archive construction robustness** (R78). Exact text equivalence is a stronger invariance contract than approximate quality differences. It should be obtained before adding any learned retrieval or expensive routing mechanism.

**Physical cost** (R73 compressed frame activations) -> **archive-read plus detector CPU cost** (R78). A source-index oracle, optional FTS5 and warm-memory reads cannot be silently equated with a deployable, cold SSD evidence retrieval service.

## Next hypothesis gates

1. If R78's archived detector input equivalence fails, debug byte offsets, Unicode, source record serialization and model input framing; do not tune the detector.
2. If it passes, compare cost under **independently retrieved source IDs** with two ordinary strong baselines: uncompressed source + FTS5/BM25 and whole-source compressed + conventional lookup. Charge retrieval, index bytes, source reader, model compute and answer quality jointly.
3. Evaluate a **previously unseen task or corpus** for semantic grounding; R76 shares its detector training domain with RAGTruth, so success there cannot substantiate out-of-domain robustness.
4. Distinguish answer-level and atomic-claim errors. A high recall from warn-all or weak evidence matching is not useful without explicit false-positive and abstention analysis.
5. Prefer a simplification or negative result if conventional retrieval+versioned source receipts Pareto-dominates CDG on real tasks.

## Publication discipline

Use \`[FACT]\` only for measured code/CI outputs, \`[INFERENCE]\` for constrained interpretation, and \`[UNCERTAIN]\` for hypotheses. The thesis of faster, smaller, more faithful end-to-end RAG is **not yet demonstrated**. Keep original RAGTruth texts and model weights with their upstream owners.
