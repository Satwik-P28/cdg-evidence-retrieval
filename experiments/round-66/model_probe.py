#!/usr/bin/env python3
"""Resolve public model identity once before pinning the Round 66 reader."""
import hashlib,json
from urllib.request import Request,urlopen
URL="https://huggingface.co/api/models/deepset/tinyroberta-squad2"
with urlopen(Request(URL,headers={"User-Agent":"CDG-research-source-identity/1.0"}),timeout=80) as r:
    body=r.read(300000)
data=json.loads(body)
sha=data["sha"]
assert len(sha)==40 and all(c in "0123456789abcdef" for c in sha)
print("ROUND66_MODEL_IDENTITY",json.dumps({
  "model":"deepset/tinyroberta-squad2",
  "sha":sha,
  "pipeline_tag":data.get("pipeline_tag"),
  "card_license":(data.get("cardData") or {}).get("license"),
  "model_api_sha256":hashlib.sha256(body).hexdigest(),
  "siblings":[x["rfilename"] for x in data.get("siblings",[]) if x.get("rfilename","").endswith((".safetensors",".bin",".json"))][:24]
},sort_keys=True))
