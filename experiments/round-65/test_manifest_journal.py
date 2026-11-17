import unittest
from manifest_journal import (packet,replay,pack_journal,experiment,load,
                              CHECKPOINT_INTERVALS,R64,R46,R47,R63)


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.r64=load('cdg64test65',R64)
        self.r46=load('cdg46test65',R46)
        self.r47=load('cdg47test65',R47)
        self.r63=load('cdg63test65',R63)
        self.docs=[
            ('history',b'A long shared project README '*60+b'first version'),
            ('history',b'A long shared project README '*60+b'second version'),
            ('independent',b'unrelated note with unique text.'),
        ]
        self.archive=self.r64.StreamingArchive(
            self.docs,'threshold_migration',self.r46.frame,self.r47,self.r63.windows)

    def test_event_order_and_full_replay(self):
        self.assertGreater(len(self.archive.events),len(self.docs))
        for interval in CHECKPOINT_INTERVALS+(1,2):
            blob=pack_journal(self.archive.events,self.r47,interval)
            self.assertEqual(blob['final_state'],self.archive.manifests)
            self.assertEqual(replay(blob['snapshot'],blob['tail'],self.r47),
                             self.archive.manifests)
            self.assertGreater(blob['total_metadata_written_bytes'],0)

    def test_partial_and_corrupted_event_detected(self):
        raw=packet(self.archive.events[0])
        with self.assertRaises(ValueError):
            replay(b'',raw[:-3],self.r47)
        damaged=bytearray(raw)
        damaged[-1]^=1
        with self.assertRaises(ValueError):
            replay(b'',bytes(damaged),self.r47)
        with self.assertRaises(ValueError):
            replay(b'',raw[:19],self.r47)

    def test_source_reference_invalid_events(self):
        template=self.archive.manifests[0]
        with self.assertRaises(ValueError):
            replay(b'',packet({'op':'replace','index':0,'manifest':template}),
                   self.r47)
        with self.assertRaises(ValueError):
            replay(b'',packet({'op':'append','index':5,'manifest':template}),
                   self.r47)
        with self.assertRaises(ValueError):
            pack_journal(self.archive.events,self.r47,0)

    def test_journal_vs_full_rewrite_cost(self):
        more=[('independent',f'completely separate paragraph {i}'.encode())
              for i in range(60)]
        obj=self.r64.StreamingArchive(self.docs+more,'threshold_migration',
                                      self.r46.frame,self.r47,self.r63.windows)
        compressed=pack_journal(obj.events,self.r47,32)
        self.assertLess(compressed['total_metadata_written_bytes'],
                        obj.manifest_rewrite_bytes)
        self.assertEqual(compressed['final_state'],obj.manifests)

    def test_small_joint_matrix(self):
        h={'ruff':[{'data':self.docs[0][1]},
                   {'data':self.docs[1][1]}]}
        independent=[('independent',f'independent {i}'.encode())
                     for i in range(512)]
        import manifest_journal as m
        before=m.INDEPENDENT_COUNTS
        m.INDEPENDENT_COUNTS=(128,)
        try:result=experiment(h,independent)
        finally:m.INDEPENDENT_COUNTS=before
        self.assertEqual(len(result['rows']),len(CHECKPOINT_INTERVALS)*2)
        for row in result['rows']:
            self.assertGreater(row['journal_total_archive_bytes'],0)
            self.assertGreater(row['manifest_journal_written_bytes'],0)
            self.assertEqual(row['source_count'],130)

if __name__=='__main__':unittest.main()
