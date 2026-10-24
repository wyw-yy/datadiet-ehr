"""List Qwen2.5-1.5B-Instruct files on ModelScope and write a fetch manifest."""
import json
import urllib.request
from pathlib import Path

MODEL = "qwen/Qwen2.5-1.5B-Instruct"
ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "models" / "Qwen2.5-1.5B-Instruct"

api = (f"https://modelscope.cn/api/v1/models/{MODEL}/repo/files"
       f"?Revision=master&Recursive=true")
req = urllib.request.Request(api, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=60) as r:
    payload = json.loads(r.read())

files = payload.get("Data", {}).get("Files", [])
print("files:", len(files))
items = []
for f in files:
    name, size, ftype = f.get("Name"), f.get("Size", 0), f.get("Type")
    if ftype != "blob":
        continue
    if name.endswith(".md") or name.startswith("."):
        continue
    url = (f"https://modelscope.cn/api/v1/models/{MODEL}/repo"
           f"?Revision=master&FilePath={urllib.parse.quote(name)}")
    items.append({"url": url, "dest": str(DEST / name), "size": int(size)})
    print(f"  {name:42s} {size/1e6:8.2f} MB")

manifest = ROOT / "tools" / "manifest_model15.json"
manifest.write_text(json.dumps(items, indent=2), encoding="utf-8")
print("wrote", manifest)
