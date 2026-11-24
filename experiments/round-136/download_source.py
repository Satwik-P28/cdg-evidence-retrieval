"""Select one exact public NewsEdits artifact, without downloading the entire folder."""
import argparse,gzip,hashlib,json,shutil
from pathlib import Path
import gdown
FOLDER="https://drive.google.com/drive/folders/17a5S3liA0C91XbgnMBUQBo-NVb22Z9xf"

def main(out):
    out.mkdir(parents=True,exist_ok=True)
    items=gdown.download_folder(url=FOLDER,output=str(out)+"/",skip_download=True,quiet=False,remaining_ok=True)
    if not items:raise RuntimeError("public folder inaccessible; use workflow file_id override")
    # Upstream demo explicitly identifies AP matched sentence DB.
    candidates=[x for x in items if Path(x.path).name.lower() in {"ap-matched-sentences.db","ap-matched-sentences.db.gz"}]
    if len(candidates)!=1:raise RuntimeError("expected exactly one AP artifact; candidates="+repr([(x.id,x.path) for x in items]))
    item=candidates[0]
    download(item.id,Path(item.path).name,out)

def download(id,name,out):
    out.mkdir(parents=True,exist_ok=True)
    dest=out/Path(name).name
    if not gdown.download(id=id,output=str(dest),quiet=False):raise RuntimeError("download failed")
    if dest.name.endswith(".gz"):
        with gzip.open(dest,"rb") as a,(out/"ap.db").open("wb") as b:shutil.copyfileobj(a,b)
    else:dest.replace(out/"ap.db")
    (out/"source.json").write_text(json.dumps(dict(file_id=id,filename=name,folder=FOLDER),indent=2))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--out",type=Path,required=True);p.add_argument("--file-id",default="");p.add_argument("--filename",default="ap-matched-sentences.db.gz");a=p.parse_args()
    if a.file_id:download(a.file_id,a.filename,a.out)
    else:main(a.out)
