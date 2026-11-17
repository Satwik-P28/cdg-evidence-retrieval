import hashlib
import unittest
from version_chunks import FramedArchive,DeltaArchive,frame,load_source,evaluate


class TestChunkArchive(unittest.TestCase):
    def test_segments_reassemble_exact_bytes(self):
        data=('first line 😊\nsecond line café\n'*300).encode()
        for mode in ('whole','fixed512','fixed2048','gear512','gear1024','line512'):
            self.assertEqual(b''.join(frame(data,mode)),data,mode)
            engine=FramedArchive([data,data+b'end\n'],mode)
            self.assertEqual(engine.read(0)[0],data)
            self.assertEqual(engine.read(1)[0],data+b'end\n')
            self.assertEqual(engine.read(1,5,300)[0],(data+b'end\n')[5:300])

    def test_diff_chain_and_checkpoints(self):
        src=[b'abcdefg\n',b'abXdefg\n',b'abXdefg\nappend\n',
             b'abXdefg\nappend\nY',b'abXdefg\nappend\nYZ']
        for interval in (2,3,5):
            obj=DeltaArchive(src,interval)
            for i,blob in enumerate(src):
                self.assertEqual(obj.read(i)[0],blob)
                self.assertEqual(obj.read(i,1,4)[0],blob[1:4])

    def test_checksum_catches_corruption(self):
        obj=FramedArchive([b'evidence strong\n'],'fixed512')
        key=next(iter(obj.frames))
        obj.frames[key]=b'corrupt'
        with self.assertRaises(Exception):
            obj.read(0)

    def test_real_revision_input_and_full_evaluation(self):
        versions=load_source()
        self.assertEqual(len(versions),12)
        result=evaluate(versions,span_size=100,queries_per_version=3)
        self.assertEqual(result['sampled_span_queries'],36)
        self.assertEqual(len(result['strategies']),8)
        self.assertGreater(result['git_control']['pack_and_index_bytes'],0)

    def test_empty_and_short_frame(self):
        for mode in ('whole','fixed512','gear512','line512'):
            archive=FramedArchive([b'',b'x'],mode)
            self.assertEqual(archive.read(0)[0],b'')
            self.assertEqual(archive.read(1)[0],b'x')

if __name__=='__main__':
    unittest.main()
