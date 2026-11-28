"""R181: rejection may only remove impossible candidates, and corruption must raise."""
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[0].parent / "round-158"))

import rejection  # noqa: E402


def test_varint_roundtrip():
    values = [0, 1, 127, 128, 300, 1 << 20, (1 << 63) - 1]
    assert rejection.read_varints(rejection.varint_bytes(values), len(values)) == values


def test_varint_rejects_truncated_payload():
    raw = rejection.varint_bytes([1, 2, 300])
    with pytest.raises(ValueError):
        rejection.read_varints(raw[:-1], 3)


def test_pair_posting_decodes_to_the_original_document_ids():
    """The stored list is first-id plus deltas; decoding must re-accumulate."""
    import sqlite3
    cids = [5, 100, 1000]
    body = rejection.varint_bytes([cids[0]] + [b - a for a, b in zip(cids, cids[1:])])
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE pair_postings(pid INTEGER PRIMARY KEY, df INTEGER, body BLOB)")
    db.execute("INSERT INTO pair_postings VALUES(?,?,?)",
               (rejection.pair_key("alpha", "beta"), len(cids), body))
    filters = rejection.Filters(db)
    assert filters.pair_set("alpha", "beta") == set(cids)


def test_varint_rejects_count_mismatch():
    raw = rejection.varint_bytes([1, 2, 3])
    with pytest.raises(ValueError):
        rejection.read_varints(raw, 2)


def test_pair_key_is_stable_and_ordered():
    assert rejection.pair_key("alpha", "beta") == rejection.pair_key("alpha", "beta")
    assert rejection.pair_key("alpha", "beta") != rejection.pair_key("beta", "alpha")
    assert 0 <= rejection.pair_key("alpha", "beta") < (1 << 63)


class FakeFilters(rejection.Filters):
    def __init__(self, pairs=None, bits=None, selective=False):
        self.db = None
        self.pair_cache = {}
        self.bits = None
        self.work = __import__("collections").Counter()
        self._pairs = pairs or {}
        self._bits = bits
        self.selective = selective

    def has_pairs(self):
        return bool(self._pairs)

    def has_bits(self):
        return self._bits is not None

    def pair_set(self, a, b):
        return self._pairs.get((a, b))

    def mask(self, cid):
        return self._bits[cid]


def test_rejection_removes_only_documents_without_the_pair():
    filters = FakeFilters(pairs={("alpha", "beta"): {2, 3}})
    kept = filters.reject(["alpha", "beta"], {1, 2, 3, 4})
    assert kept == {2, 3}


def test_missing_pair_removes_every_candidate():
    # In a complete index a pair that occurs nowhere cannot be part of any phrase.
    filters = FakeFilters(pairs={("alpha", "beta"): None})
    assert filters.reject(["alpha", "beta"], {1, 2, 3}) == set()


def test_selective_index_missing_pair_is_not_evidence_of_absence():
    # The same missing row in a selective index only means "not stored".
    # Confusing the two is how a filter becomes unsound.
    filters = FakeFilters(pairs={("alpha", "beta"): None}, selective=True)
    assert filters.reject(["alpha", "beta"], {1, 2, 3}) == {1, 2, 3}
    assert filters.work["pairs_unindexed"] == 1


def test_fingerprint_only_rejects_on_a_clear_bit():
    # Document 1 has hash bit set for ("alpha","beta"), document 2 does not.
    k = rejection.pair_key("alpha", "beta") % 64
    masks = {1: bytearray(8), 2: bytearray(8), 3: bytearray(8)}
    masks[1][k >> 3] |= 1 << (k & 7)
    masks[3][k >> 3] |= 1 << (k & 7)
    filters = FakeFilters(bits=masks)
    assert filters.reject(["alpha", "beta"], {1, 2, 3}) == {1, 3}


def test_rejection_never_adds_candidates():
    filters = FakeFilters(pairs={("a", "b"): {1, 2, 9}})
    assert filters.reject(["a", "b"], {1}) == {1}


def test_select_pairs_buys_rejection_per_byte():
    import sqlite3
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE pair_postings(pid INTEGER PRIMARY KEY, df INTEGER, body BLOB)")
    db.execute("CREATE TABLE revisions(g INTEGER PRIMARY KEY, cid INTEGER)")
    db.executemany("INSERT INTO revisions VALUES(?,?)", [(g, g) for g in range(1, 101)])
    db.executemany("INSERT INTO pair_postings VALUES(?,?,?)",
                   [(1, 90, b"x" * 100), (2, 2, b"y" * 100), (3, 50, b"z" * 100)])
    keep = rejection.select_pairs(db, 250)  # two rows at 124 bytes each
    assert len(keep) == 2
    # A pair present in 2 of 100 documents rejects ~98% of candidates; one present in 90
    # rejects ~10%.  The rare pair must be bought first.
    assert 2 in keep and 1 not in keep


def test_select_pairs_returns_everything_without_a_budget():
    assert rejection.select_pairs(None, None) is None
