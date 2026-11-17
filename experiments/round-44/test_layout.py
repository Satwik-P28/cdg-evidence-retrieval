import tempfile
import unittest
from pathlib import Path
from layout_lab import Variant, blocks, exercise


class Round44Tests(unittest.TestCase):
    def test_equal_line_identity_and_utf8(self):
        data={'a':'café 😊 evidence\nrepeat repeat\nrepeat repeat\n'.encode(),
              'b':'café 😊 evidence\nrepeat repeat\n'.encode()}
        with tempfile.TemporaryDirectory() as home:
            for i,mode in enumerate(('legacy','delete','trigger')):
                engine=Variant(Path(home)/str(i),data,mode=mode,diff='edges',history='all')
                self.assertEqual(sorted(name for name,_ in engine.search('evidence')),['a','b'])
                engine.update({'a':b'prefix\n'+data['a'],'b':data['b']})
                self.assertEqual(engine.read_gen(0,'a'),data['a'])
                self.assertEqual(engine.read_gen(1,'a'),b'prefix\n'+data['a'])
                self.assertEqual(engine.search_gen(0,'evidence'),['a','b'])
                engine.close()

    def test_deletion_rename_and_historic_lookup(self):
        with tempfile.TemporaryDirectory() as home:
            for i in range(6):
                mode=('legacy','delete','trigger')[i%3]
                history=('all','live-only')[i//3]
                engine=Variant(Path(home)/str(i),
                               {'old':b'evidence original\n','keep':b'algorithm source\n'},
                               mode=mode,diff='edges',history=history)
                engine.update({'new':b'changed evidence\n','keep':b'algorithm source\n'})
                self.assertEqual(sorted(name for name,_ in engine.search('evidence')),['new'])
                self.assertEqual(engine.search_gen(0,'evidence'),['old'])
                self.assertEqual(engine.read_gen(0,'old'),b'evidence original\n')
                engine.close()

    def test_diff_policies_preserve_retrieval_parity(self):
        src=b'alpha evidence\nsame same\nsame same\nomega\n'
        with tempfile.TemporaryDirectory() as home:
            engines=[Variant(Path(home)/str(i),{'d':src},mode=m,diff=diff,history='all')
                     for i,(m,diff) in enumerate((('legacy','sequence'),
                       ('legacy','edges'),('delete','edges'),
                       ('trigger','edges'),('delete','rebuild')))]
            for changed in (b'alpha evidence\nsame same\nadded insertion\nsame same\nomega\n',
                            b'alpha proof\nsame same\nomega\n',
                            b'not here anymore\n'):
                for e in engines:
                    e.update({'d':changed})
                for token in ('evidence','proof','added','same','omega','anymore'):
                    result=[len(e.search(token)) for e in engines]
                    self.assertEqual(len(set(result)),1,(token,result))
            for e in engines:
                self.assertEqual(e.read_gen(0,'d'),src)
                e.close()

    def test_edgebased_diff_handles_duplicates(self):
        old=['x','x','a','x','x']
        new=['x','x','a','b','x','x']
        op=list(blocks(old,new,'edges'))
        self.assertEqual(op,[('equal',0,3,0,3),('replace',3,3,3,4),
                             ('equal',3,5,4,6)])
        self.assertEqual(list(blocks([],[], 'edges')),[])

    def test_historical_index_storage_tradeoff(self):
        with tempfile.TemporaryDirectory() as home:
            docs={'x':b'algorithm evidence\n'*30}
            a=Variant(Path(home)/'a',docs,mode='delete',diff='edges',history='all')
            b=Variant(Path(home)/'b',docs,mode='delete',diff='edges',history='live-only')
            for n in range(3):
                new={'x':docs['x']+f'new {n}\n'.encode()}
                a.update(new);b.update(new)
            self.assertLess(b.total_bytes(),a.total_bytes())
            self.assertEqual(a.search_gen(0,'algorithm'),b.search_gen(0,'algorithm'))
            a.close();b.close()

    def test_smoke_replicated_corpus(self):
        result=exercise(5,.2,11,'replace',steps=2)
        self.assertEqual(len(result['update_p50_ms']),6)
        self.assertEqual(len(result['history_search_p50_us']),6)

if __name__=='__main__':
    unittest.main()
