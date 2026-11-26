import os
from physical_io import measured,summary

def test_pread_accounting(tmp_path):
    p=tmp_path/"a";p.write_bytes(b"abcdef");fd=os.open(p,os.O_RDONLY)
    try:
        value,m=measured(lambda:os.pread(fd,4,1),fd)
        assert value==b"bcde" and m["sidecar_pread_calls"]==1
        assert m["sidecar_requested_bytes"]==m["sidecar_returned_bytes"]==4
        assert summary([m])["sidecar_returned_bytes"]["total"]==4
    finally:os.close(fd)
