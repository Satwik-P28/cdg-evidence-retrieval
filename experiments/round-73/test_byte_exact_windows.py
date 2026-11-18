import hashlib,re,unittest
from byte_exact_windows import (
    WORD_WIDTH,WORD_STRIDE,MAX_WINDOWS,
    source_byte_windows,lexical_window_rank,frame_ids,load,R48,R69
)


class ByteWindowTests(unittest.TestCase):
    def setUp(self):
        self.r69=load('r69_test73',R69)
        self.r48=load('r48_test73',R48)

    def test_utf8_and_spacing_are_exactly_reversible(self):
        source='café naïve\tBerlin\nParis   Madrid. 北京 café London'
        blobs=source.encode('utf8')
        windows=source_byte_windows(source)
        self.assertEqual(len(windows),1)
        raw=blobs[windows[0].byte_start:windows[0].byte_end].decode('utf8')
        self.assertEqual(' '.join(raw.split()),windows[0].normalized)
        self.assertEqual(
            windows[0].normalized,
            ' '.join(re.findall(r'\S+',source)))

    def test_overlapping_positions_match_r72_window_contract(self):
        source=' '.join('token'+str(i) for i in range(1000))
        windows=source_byte_windows(source)
        self.assertEqual(len(windows),10)
        raw=re.findall(r'\S+',source)
        for i,window in enumerate(windows):
            self.assertEqual(window.normalized,
                             ' '.join(raw[i*WORD_STRIDE:i*WORD_STRIDE+WORD_WIDTH]))
            self.assertEqual(
                source.encode()[window.byte_start:window.byte_end].decode(),
                window.normalized)

    def test_capped_source_reads_are_reportable(self):
        source=' '.join('word'+str(i) for i in range(11000))
        windows=source_byte_windows(source)
        self.assertEqual(len(windows),MAX_WINDOWS)
        self.assertLess(windows[-1].byte_end,len(source.encode()))

    def test_lexical_source_selection_does_not_read_gold(self):
        src='The author lived in Berlin in 1998. '*60
        windows=source_byte_windows(src)
        other=source_byte_windows('The artist was born in Rome.')
        combined=windows+other
        self.assertEqual(lexical_window_rank(combined,
                                            'Where was the artist born?',
                                            self.r69)[0],len(windows))

    def test_exact_verified_cas_spans(self):
        original=[
            'The inventor lived in Berlin.\nThe painter lived in Rome.',
            'Café owner was in Paris, then returned to Berlin.'
        ]
        raw=[s.encode('utf8') for s in original]
        for mode in ('whole','gear512'):
            reader=self.r48.VersionedReader(raw,mode,'binary-zlib')
            for generation,source in enumerate(original):
                for window in source_byte_windows(source):
                    receipt=reader.receipt(generation,window.byte_start,window.byte_end)
                    decoded,traffic=reader.read(receipt,pin_generation=generation)
                    self.assertEqual(decoded,
                                     raw[generation][window.byte_start:window.byte_end])
                    self.assertGreater(traffic,0)
                    frames=frame_ids(reader,generation,
                                     window.byte_start,window.byte_end)
                    self.assertTrue(frames)
                    self.assertTrue(frames.issubset(reader.archive.frames))
            with self.assertRaises(ValueError):
                reader.read(reader.receipt(0,0,1),pin_generation=1)

if __name__=='__main__':
    unittest.main()
