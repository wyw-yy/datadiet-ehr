import urllib.request, urllib.error, time

urls = {
    "hf.co": "https://huggingface.co/datasets/lavita/ChatDoctor-HealthCareMagic-100k/resolve/main/data/train-00000-of-00001-5e7cb295b9cff0bf.parquet",
    "hf-mirror": "https://hf-mirror.com/datasets/lavita/ChatDoctor-HealthCareMagic-100k/resolve/main/data/train-00000-of-00001-5e7cb295b9cff0bf.parquet",
    "ms-dataset": "https://modelscope.cn/api/v1/datasets/lavita/ChatDoctor-HealthCareMagic-100k/repo?Revision=master&FilePath=data%2Ftrain-00000-of-00001-5e7cb295b9cff0bf.parquet",
    "ms-dataset2": "https://www.modelscope.cn/api/v1/datasets/AI-ModelScope/ChatDoctor-HealthCareMagic-100k/repo?Revision=master&FilePath=data%2Ftrain-00000-of-00001-5e7cb295b9cff0bf.parquet",
}
for k, u in urls.items():
    req = urllib.request.Request(u, headers={"Range": "bytes=0-1023", "User-Agent": "Mozilla/5.0"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            b = r.read(1024)
            cr = r.headers.get("Content-Range")
            cl = r.headers.get("Content-Length")
            print(f"{k:12s} status={r.status} got={len(b)} CR={cr} CL={cl} {time.time()-t0:.1f}s final={r.geturl()[:90]}")
    except urllib.error.HTTPError as e:
        print(f"{k:12s} HTTPError {e.code} {e.reason} {time.time()-t0:.1f}s")
    except Exception as e:
        print(f"{k:12s} ERR {type(e).__name__}: {e} {time.time()-t0:.1f}s")
