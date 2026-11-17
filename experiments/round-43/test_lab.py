import tempfile
import unittest
from pathlib import Path
from lab import IndexedDelta, nonnoop_edit

class Round43Tests(unittest.TestCase):
    def test_non_noop_replace_after_fourth_step(self):
        original = b'evidence here\n'
        self.assertNotEqual(nonnoop_edit(original, 4, 'replace'), original)
        for mode in ('append', 'replace', 'insert', 'delete'):
            data = original
            for step in range(1, 9):
                out = nonnoop_edit(data, step, mode)
                self.assertNotEqual(out, data)
                data = out

    def test_indexed_insert_delete_replace_and_history(self):
        docs = {'alpha': b'evidence A\nevidence A\nfin\n',
                'beta': b'evidence A\nfin\n'}
        with tempfile.TemporaryDirectory() as path:
            engine = IndexedDelta(Path(path) / 'store', docs)
            self.assertEqual(sorted(name for name, _ in engine.search('evidence')),
                             ['alpha', 'alpha', 'beta'])
            old_rows = engine.old['alpha'][:]
            changed = {'alpha': b'evidence A\ninserted token\nevidence A\nfin\n',
                       'beta': docs['beta']}
            stat = engine.update(changed)
            self.assertGreaterEqual(stat['reused_rows'], 3)
            self.assertEqual(old_rows[0][0], engine.old['alpha'][0][0])
            self.assertEqual(old_rows[1][0], engine.old['alpha'][2][0])
            self.assertEqual(len(engine.search('inserted')), 1)
            engine.update({'alpha': b'new token\nfin\n'})
            self.assertEqual(engine.search('evidence'), [])
            self.assertEqual(engine.read_gen(0,'alpha'), docs['alpha'])
            self.assertEqual(engine.read_gen(1,'beta'), docs['beta'])
            self.assertEqual(engine.read_gen(2,'alpha'), b'new token\nfin\n')
            engine.close()

    def test_utf8_byte_preservation(self):
        with tempfile.TemporaryDirectory() as path:
            content = 'naïve 😊 evidence\n'.encode('utf8')
            engine = IndexedDelta(Path(path)/'store', {'c':content})
            self.assertEqual(engine.read_gen(0,'c'),content)
            engine.update({'c':content+b'update\n'})
            self.assertEqual(engine.read_gen(0,'c'), content)
            engine.close()

if __name__=='__main__':
    unittest.main()
