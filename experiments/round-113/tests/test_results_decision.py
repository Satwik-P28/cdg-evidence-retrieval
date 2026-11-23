"""Observed-data guard against accidentally advertising the failed planner."""
import json
from pathlib import Path


def test_primary_ci_result_and_exploratory_are_consistent():
    folder=Path(__file__).resolve().parents[1]
    original=json.loads((folder/'results-seven-arm.json').read_text())
    extra=json.loads((folder/'results-eleven-arm.json').read_text())
    a={x['policy']:x for x in original['results']}
    b={x['policy']:x for x in extra['results']}
    assert len(a)==7 and len(b)==11
    assert extra['confirmatory_first_run_policies']==list(a)
    assert len(extra['posthoc_exploratory_additional_policies'])==4
    for key,old in a.items():
        fresh=b[key]
        assert fresh['physical_source_index_sqlite_bytes']==old['physical_source_index_sqlite_bytes']
        for key in ('decoded_original_source_bytes','decoded_byte_amplification','requested_original_source_bytes','source_receipts_verified'):
            assert fresh['original_top10_source_reads'][key]==old['original_top10_source_reads'][key]
        for key in ('wal_appended_bytes','blob_rewrite_per_edited_source_byte','source_rows_after_edits_verified','matched_conventional_post_edit_top10'):
            assert fresh['synthetic_edit_stress'][key]==old['synthetic_edit_stress'][key]
    assert original['original_dev_questions']==extra['original_dev_questions']==1005
    assert original['original_dev_paragraphs']==extra['original_dev_paragraphs']==13266


def test_hash_layout_strictly_dominates_budget_30_planner():
    folder=Path(__file__).resolve().parents[1]
    d=json.loads((folder/'results-eleven-arm.json').read_text())
    r={x['policy']:x for x in d['results']}
    hash50=r['hash_50_25']; plan30=r['planner_balanced_30']
    assert all(x['original_source_receipts_verified']==13266 and x['original_query_ranking_parity']==1005 for x in r.values())
    assert hash50['physical_source_index_sqlite_bytes']<plan30['physical_source_index_sqlite_bytes']
    assert hash50['original_top10_source_reads']['decoded_original_source_bytes'] < plan30['original_top10_source_reads']['decoded_original_source_bytes']
    assert hash50['synthetic_edit_stress']['wal_appended_bytes'] < plan30['synthetic_edit_stress']['wal_appended_bytes']
    assert hash50['physical_source_index_sqlite_bytes']<8*1024*1024
    assert plan30['physical_source_index_sqlite_bytes']<8*1024*1024