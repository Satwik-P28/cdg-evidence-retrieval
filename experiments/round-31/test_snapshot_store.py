"""Functional tests of snapshot pinning, mutation and receipt integrity."""
from __future__ import annotations
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from snapshot_store import SnapshotReader,publish

class SnapshotStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='cdg-r31-unit-')
        self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)
        self.source_dir=self.home/'inputs';self.source_dir.mkdir()
        self.a=self.source_dir/'Avery.txt';self.b=self.source_dir/'Larchfield.txt'
        self.a.write_text('Avery wrote about Larchfield.txt.\nAvery collected naïve plants.\n',encoding='utf-8')
        self.b.write_text('Larchfield is a town.\nMany researchers live there.\n',encoding='utf-8')
        self.root=self.home/'archive'
    def _build(self):return publish(self.root,[self.a,self.b],frame_size=32)
    def test_first_generation_byte_exact_and_title_edges(self):
        state=self._build()
        with SnapshotReader(self.root) as r:
            self.assertEqual(state['generation'],r.generation)
            self.assertEqual(r.outgoing_links(1),[2])
            hits=r.search('naïve')
            self.assertTrue(hits)
            self.assertIn('naïve',hits[0]['text'])
            self.assertEqual(r.read_receipt(hits[0]['receipt']),hits[0]['text'].encode())
    def test_reader_pins_old_and_new_after_switch(self):
        self._build()
        old=SnapshotReader(self.root)
        try:
            original=old.search('naïve')[0]
            self.a.write_text('Avery wrote about nothing now.\nAvery collected fungi.\n',encoding='utf-8')
            newer=self._build()
            with SnapshotReader(self.root) as current:
                self.assertNotEqual(current.generation,old.generation)
                self.assertFalse(current.search('naïve'))
                self.assertEqual(current.outgoing_links(1),[])
                with self.assertRaises(ValueError):current.read_receipt(original['receipt'])
                self.assertTrue(current.search('fungi'))
            self.assertEqual(old.read_receipt(original['receipt']),original['text'].encode())
            self.assertEqual(old.outgoing_links(1),[2])
        finally:old.close()
    def test_failure_before_publish_keeps_old(self):
        old=self._build()['generation']
        self.a.write_text('Changed words only.\n',encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError,'injected failure'):
            publish(self.root,[self.a,self.b],frame_size=32,fail_before_switch=True)
        self.assertEqual((self.root/'CURRENT').read_text().strip(),old)
        with SnapshotReader(self.root) as r:self.assertTrue(r.search('naïve'))
    def test_corrupt_payload_refused_on_open(self):
        state=self._build();p=self.root/state['generation']/'frames.zst'
        with p.open('r+b') as f:f.seek(0);f.write(b'bad')
        with self.assertRaisesRegex(ValueError,'corrupt indexed snapshot'):
            SnapshotReader(self.root)
    def test_corrupt_index_refused_on_open(self):
        state=self._build();p=self.root/state['generation']/'index.sqlite'
        with p.open('r+b') as f:f.seek(100);f.write(b'bad')
        with self.assertRaisesRegex(ValueError,'corrupt indexed snapshot'):
            SnapshotReader(self.root)
    def test_receipt_digest_and_bounds(self):
        self._build()
        with SnapshotReader(self.root) as r:
            x=r.search('Avery')[0]['receipt']
            bad=dict(x,source_sha256='0'*64)
            with self.assertRaises(ValueError):r.read_receipt(bad)
            bad=dict(x,end=10**6)
            with self.assertRaises(ValueError):r.read_receipt(bad)
    def test_unchanged_replication_keeps_old_receipt_generation_bound(self):
        first=self._build()
        with SnapshotReader(self.root) as old:receipt=old.search('naïve')[0]['receipt']
        second=self._build()
        self.assertNotEqual(first['generation'],second['generation'])
        with SnapshotReader(self.root) as reader:
            with self.assertRaises(ValueError):reader.read_receipt(receipt)
    def test_missing_sources_and_duplicate_names_fail(self):
        with self.assertRaises(ValueError):publish(self.root,[],frame_size=32)
        with self.assertRaises(ValueError):publish(self.root,[self.a,self.a],frame_size=32)
    def test_stale_source_after_snapshot_only_affects_new_publication(self):
        self._build();self.a.unlink()
        with SnapshotReader(self.root) as reader:
            self.assertTrue(reader.search('naïve'))
        with self.assertRaises(FileNotFoundError):self._build()
    def test_old_freshness_is_not_claimed(self):
        self._build()
        with SnapshotReader(self.root) as old:
            self.a.write_text('Very different source.\n',encoding='utf-8')
            self.assertTrue(old.search('naïve'))
            self.assertEqual(old.manifest['contract'],'immutable physical snapshot; no origin freshness or ACL guarantee')
if __name__=='__main__':unittest.main()