"""R93 predeclared priority and train-only selection regression checks."""
import tempfile
import unittest
from pathlib import Path
from train_budget_selection import (
    POLICIES,SEEDS,train_gold_sources,title_rarity_scores,
    train_query_relevance,greedy_coverage_priority,
    source_order,source_disjoint_dev,choose_train_policy,fit_budget
)
from train_budget_selection import make_fts,annotated_gold

DOCS=[
    {"doc_id":i+1,"title":"Study mineral"+str(i),
     "abstract":["A controlled experiment on a material called mineral"+str(i)+"."]}
    for i in range(20)
]
TRAIN=[
    {"id":10,"claim":"mineral1","evidence":{
        "2":[{"label":"SUPPORT","sentences":[0]}]}},
    {"id":20,"claim":"mineral2","evidence":{
        "3":[{"label":"CONTRADICT","sentences":[0]}]}},
    {"id":30,"claim":"mineral3","evidence":{}},
]
DEV=[
    {"id":50,"claim":"mineral1 phenomenon","evidence":{
        "2":[{"label":"SUPPORT","sentences":[0]}]}},
    {"id":60,"claim":"mineral5 phenomenon","evidence":{
        "6":[{"label":"CONTRADICT","sentences":[0]}]}},
]


class TrainedBudgetTests(unittest.TestCase):
    def test_train_gold_weights_do_not_read_dev_labels(self):
        counts=train_gold_sources(TRAIN,{str(x["doc_id"]) for x in DOCS})
        self.assertEqual(counts["2"],1)
        self.assertEqual(counts["3"],1)
        self.assertEqual(counts["6"],0)

    def test_dev_gold_source_disjoint_filter(self):
        labels=annotated_gold(DEV,DOCS)
        disjoint=source_disjoint_dev(labels,{"2","3"})
        self.assertEqual(len(disjoint),1)
        self.assertEqual(disjoint[0]["id"],"60")

    def test_query_rank_only_uses_claim_text_and_not_labels(self):
        scores,links,meta=train_query_relevance(DOCS,TRAIN)
        altered=[{**r,"evidence":{}} for r in TRAIN]
        scores2,links2,_=train_query_relevance(DOCS,altered)
        self.assertEqual(scores,scores2)
        self.assertEqual(links,links2)
        self.assertFalse(meta["query_uses_gold_labels"])

    def test_greedy_covers_different_claims_and_is_deterministic(self):
        relevance={
            "1":{0:1.0},"2":{0:0.7},"3":{1:1.0},
            "4":{2:0.8},"5":{2:0.6}
        }
        choices=greedy_coverage_priority(DOCS,relevance)
        self.assertEqual(choices,greedy_coverage_priority(DOCS,relevance))
        self.assertEqual(len(choices),3)
        self.assertIn("1",choices)
        self.assertIn("3",choices)
        self.assertIn("4",choices)

    def test_all_priorities_are_identity_preserving(self):
        rrf,links,_=train_query_relevance(DOCS,TRAIN)
        signals={
            "train_gold":train_gold_sources(
                TRAIN,{str(x["doc_id"]) for x in DOCS}),
            "train_rrf":rrf,
            "greedy":greedy_coverage_priority(DOCS,links),
            "title_rarity":title_rarity_scores(DOCS)
        }
        for policy in POLICIES:
            for seed in SEEDS:
                ordered=source_order(DOCS,policy,seed,signals)
                self.assertEqual(
                    {str(x["doc_id"]) for x in ordered},
                    {str(x["doc_id"]) for x in DOCS})
                self.assertEqual(
                    ordered,source_order(DOCS,policy,seed,signals))

    def test_train_selector_never_uses_dev_outcomes(self):
        rows=[]
        for seed in SEEDS:
            rows.extend([
                {"policy":"hash","seed":seed,"budget_bytes":999,
                 "train_r10":2,"train_r1":1,"dev_r10":99},
                {"policy":"train_evidence_frequency","seed":seed,
                 "budget_bytes":999,"train_r10":9,"train_r1":8,"dev_r10":0},
            ])
        with self.assertRaises(AssertionError):
            choose_train_policy(rows,999)  # all six policies are required
        for method in POLICIES[2:]:
            rows.extend({"policy":method,"seed":seed,
                         "budget_bytes":999,"train_r10":3,
                         "train_r1":2,"dev_r10":100}
                        for seed in SEEDS)
        choice=choose_train_policy(rows,999)
        self.assertEqual(choice["selected_policy"],
                         "train_evidence_frequency")

    def test_budget_fit_enforces_actual_sqlite_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            d=Path(root)
            c,_=make_fts(d/"five.sqlite",DOCS[:5],False)
            c.close()
            budget=(d/"five.sqlite").stat().st_size
            n,size=fit_budget(d,DOCS,budget,{})
            self.assertGreaterEqual(n,5)
            self.assertLessEqual(size,budget)

    def test_no_duplicate_dev_or_gold_case_identity(self):
        cases=annotated_gold(DEV,DOCS)
        self.assertEqual(len(cases),2)
        self.assertEqual(len({c["id"] for c in cases}),2)


if __name__=="__main__":
    unittest.main()
