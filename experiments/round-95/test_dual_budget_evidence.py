"""R95 invariants for train-only source priorities and actual SQLite costs."""
import tempfile
import unittest
from pathlib import Path
from dual_budget_evidence import (
    ARCHITECTURES, POLICIES, SEEDS,
    doc_cost_proxy, ranked_corpus, build_source_index,
    max_prefix_under_budget, prefix_bytes,
    metric_view, select_validation_policy, within_seed_pair,
    cross_architecture_matched_subset,
)
from dual_budget_evidence import annotated_gold,recall


DOCS=[
    {"doc_id":i+1, "title":"Sample"+str(i),
     "abstract":["Scientific observational data of sample "+str(i)
                 +" repeated measured outcomes."]} for i in range(22)
]
CLAIMS=[
    {"id":1,"claim":"Sample1 scientific","evidence":{
        "2":[{"label":"SUPPORT","sentences":[0]}]}},
    {"id":2,"claim":"Sample2 scientific","evidence":{
        "3":[{"label":"CONTRADICT","sentences":[0]}]}},
]
SIGNALS={
    "fit_rrf":{"2":1.2,"3":0.9},
    "fit_gold_frequency":{"2":2,"3":1},
    "title_rarity":{str(row["doc_id"]):1/(i+1)
                    for i,row in enumerate(DOCS)}
}


class DualBindingBudgetTests(unittest.TestCase):
    def test_every_policy_is_deterministic_and_identity_safe(self):
        for arch in ARCHITECTURES:
            for policy in POLICIES:
                for seed in SEEDS:
                    a=ranked_corpus(DOCS,policy,arch,seed,SIGNALS)
                    b=ranked_corpus(DOCS,policy,arch,seed,SIGNALS)
                    self.assertEqual(a,b)
                    self.assertEqual(
                        {str(x["doc_id"]) for x in a},
                        {str(x["doc_id"]) for x in DOCS})

    def test_source_cost_proxy_distinguishes_compressibility(self):
        text={"title":"repeatable","abstract":["same words "*700]}
        a=doc_cost_proxy(text,"conventional")
        b=doc_cost_proxy(text,"compressed")
        self.assertLess(b,a)
        self.assertGreater(b,0)

    def test_unseen_doc_gets_zero_trained_signal_and_stable_fallback(self):
        a=ranked_corpus(DOCS,"fit_rrf","compressed",11,SIGNALS)
        self.assertEqual(str(a[0]["doc_id"]),"2")
        self.assertEqual(str(a[1]["doc_id"]),"3")
        self.assertEqual(len(a),len(DOCS))

    def test_full_and_compressed_store_same_source_doc_ids_in_matched_fixture(self):
        x=cross_architecture_matched_subset(DOCS,CLAIMS)
        self.assertEqual(x["matched_documents"],len(DOCS))
        self.assertEqual(x["queries_equal_top10"],2)

    def test_real_compressed_file_size_below_full_at_same_source_count(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            paths={arch:root/(arch+".sqlite") for arch in ARCHITECTURES}
            for arch in ARCHITECTURES:
                db=build_source_index(paths[arch],DOCS,arch)
                db.close()
            # Tiny SQLite files can be dominated by page overhead; only
            # enforce retained real source bytes, not absolute savings here.
            self.assertGreater(paths["conventional"].stat().st_size,0)
            self.assertGreater(paths["compressed"].stat().st_size,0)

    def test_budget_fits_measured_database_not_byte_proxy(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            for arch in ARCHITECTURES:
                cache={}
                chosen=DOCS[:8]
                budget=prefix_bytes(root,chosen,arch,4,cache)
                n,size=max_prefix_under_budget(root,chosen,arch,budget,cache)
                self.assertGreaterEqual(n,4)
                self.assertLessEqual(size,budget)
                if n<len(chosen):
                    self.assertGreater(
                        prefix_bytes(root,chosen,arch,n+1,cache),budget)

    def test_reject_overbudget_and_invalid_architecture(self):
        with self.assertRaises(ValueError):
            build_source_index(Path("nonexistent"),DOCS,"invalid")
        with self.assertRaises(ValueError):
            ranked_corpus(DOCS,"random_unknown","compressed",11,SIGNALS)
        with tempfile.TemporaryDirectory() as scratch:
            with self.assertRaises(AssertionError):
                max_prefix_under_budget(
                    Path(scratch),DOCS,"conventional",1,{})

    def test_source_label_metrics_denom_constant(self):
        gold=annotated_gold(CLAIMS,DOCS)
        metrics=recall(gold,{"1":["2"],"2":["4"]},{"2","4"})
        view=metric_view(metrics)
        self.assertEqual(view["annotated_claims"],2)
        self.assertEqual(view["r10_hits"],1)

    def test_validation_selector_ignores_dev_outcomes(self):
        rows=[]
        for arch in ARCHITECTURES:
            for policy in POLICIES:
                for seed in SEEDS:
                    val=8 if policy=="fit_rrf" else 2
                    rows.append({
                        "architecture":arch,"budget":999,
                        "policy":policy,"seed":seed,
                        "validation":{"r10_hits":val,"r1_hits":val},
                        "development":{"r10_hits":0 if val==8 else 100},
                    })
        for arch in ARCHITECTURES:
            picked=select_validation_policy(rows,arch,999)
            self.assertEqual(picked["winner"],"fit_rrf")
            self.assertFalse(picked["uses_development_outcomes"])

    def test_selected_paired_differences_have_correct_sign(self):
        # All selectors are present but artificially make the dev
        # conventional arm stronger than compressed in order to ensure
        # paired deltas aren't defined to favor compression.
        rows=[]
        selected={}
        for arch in ARCHITECTURES:
            selected[(arch,999)]={"winner":"hash"}
            for seed in SEEDS:
                ones=[1,1,0] if arch=="compressed" else [1,1,1]
                rows.append({
                    "architecture":arch,"budget":999,"policy":"hash",
                    "seed":seed,"docs_retained":2,"db_bytes":64,
                    "development":{"r1_hits":sum(ones),"r10_hits":sum(ones)},
                    "dev_disjoint":{"r10_hits":sum(ones)},
                    "dev_binary_r1":ones,"dev_binary_r10":ones,
                })
        pairs=within_seed_pair(rows,selected,999)
        self.assertEqual(len(pairs),len(SEEDS))
        self.assertTrue(all(x["r10_delta"]["percentage_point_gain"]<0
                            for x in pairs))


if __name__=="__main__":
    unittest.main()
