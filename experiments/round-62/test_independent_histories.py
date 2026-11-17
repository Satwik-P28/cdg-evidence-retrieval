import hashlib,json,unittest
from unittest.mock import patch, MagicMock
from independent_histories import (PINNED,POLICIES,get,git_blob_sha,download_history,
                                    history_identity,sha,run_matrix)


class HistoryTests(unittest.TestCase):
    def test_pinned_heads_and_upstream_licenses(self):
        self.assertEqual(set(PINNED),{'ruff','transformers','flask'})
        for x in PINNED.values():
            self.assertEqual(len(x['cutoff']),40)
            self.assertEqual(x['path'],'README.md')
            self.assertTrue(x['license'])

    def test_github_token_sent_to_api_only(self):
        class FakeResponse:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,*args):return b'ok'
        captured=[]
        def fake_open(request,timeout=None):
            captured.append(request)
            return FakeResponse()
        with patch.dict('os.environ',{'GITHUB_TOKEN':'temporary-test-secret'}):
            with patch('independent_histories.urlopen',side_effect=fake_open):
                self.assertEqual(get('https://api.github.com/repos/example/repo/commits'),b'ok')
                self.assertEqual(get('https://raw.githubusercontent.com/example/repo/abc/README.md'),b'ok')
                self.assertEqual(get('https://example.com/other'),b'ok')
        self.assertEqual(captured[0].get_header('Authorization'),'Bearer temporary-test-secret')
        self.assertIsNone(captured[1].get_header('Authorization'))
        self.assertIsNone(captured[2].get_header('Authorization'))

    def test_history_commit_order_content_verification_and_noop(self):
        commits=[f'{i:040x}' for i in range(1,6)]
        entries=[{'sha':c,'commit':{'committer':{'date':'2025-01-01T00:00:00Z'}}}
                 for c in commits]
        blobmap={
            commits[0]:b'latest readme\n',
            commits[1]:b'middle readme\n',
            commits[2]:b'middle readme\n', # no-op metadata update
            commits[3]:b'earliest readme\n',
            commits[4]:b'extra old readme\n'}
        def fetch(url):
            if 'api.github.com' in url:
                return json.dumps(entries).encode()
            for commit,raw in blobmap.items():
                if commit in url:return raw
            raise AssertionError('unknown fixture URL')
        spec={'repo':'example/repo','cutoff':commits[0],'path':'README.md'}
        found=download_history(spec,count=3,get_fn=fetch)
        self.assertEqual([x['data'] for x in found],
                         [b'earliest readme\n',b'middle readme\n',b'latest readme\n'])
        self.assertEqual(found[1]['git_blob'],git_blob_sha(found[1]['data']))
        self.assertEqual(len(history_identity(found)),64)
        self.assertEqual(sha(found[0]['data']),hashlib.sha256(found[0]['data']).hexdigest())

    def test_tiny_changed_histories_archive_parity(self):
        histories={
            'ruff':[{'data':b'foo documentation\n'*40+b'v1'}]*2+
                   [{'data':b'foo documentation\n'*40+b'v2'}],
            'transformers':[{'data':b'bar manual\n'*30+b'x'},
                            {'data':b'bar manual\n'*30+b'y'},
                            {'data':b'bar manual\n'*30+b'z'}],
            'flask':[{'data':b'flask abc\n'*20+b'a'},
                     {'data':b'flask abc\n'*20+b'b'},
                     {'data':b'flask abc\n'*20+b'c'}]}
        # Include the same immutable provenance schema as downloaded API records.
        for name,entries in histories.items():
            for i,entry in enumerate(entries):
                blob=entry['data']
                entry.update({'commit':f'{i+1:040x}','sha256':sha(blob),
                              'git_blob':git_blob_sha(blob),'bytes':len(blob),
                              'date':'2025-01-01T00:00:00Z'})
        # Exercise matrix with tiny fixture independent sources, not live data.
        import independent_histories as m
        old=m.IND_COUNTS
        m.IND_COUNTS=(0,2)
        sources=[('independent',b'independent doc one'),
                 ('independent',b'independent doc two')]
        try:
            out=run_matrix(histories,sources,'fixture')
        finally:
            m.IND_COUNTS=old
        self.assertEqual(len(out['scenarios']),6)
        for row in out['scenarios']:
            self.assertEqual(set(row['policies']),set(POLICIES))
            self.assertEqual(row['policies']['all_whole']['archive_delta_pct_vs_whole'],0.0)
            self.assertGreater(row['policies']['all_whole']['archive_bytes'],0)

if __name__=='__main__': unittest.main()
